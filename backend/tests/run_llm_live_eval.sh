#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
API="$BASE_URL/api/v1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PDF_ROOT="${PDF_ROOT:-$BACKEND_DIR/tests/test_doc}"
PDF_NAME_FILTER="${PDF_NAME_FILTER:-}"
MAX_PDFS="${MAX_PDFS:-0}"
CLEANUP_PROJECT="${CLEANUP_PROJECT:-0}"
TS="$(date +%Y%m%d_%H%M%S)"
OUT_DIR="$BACKEND_DIR/tests/llm_eval_results/$TS"

mkdir -p "$OUT_DIR/requests" "$OUT_DIR/responses" "$OUT_DIR/sse"

echo "[INFO] output dir: $OUT_DIR"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "[ERROR] missing command: $1" >&2
    exit 1
  fi
}

require_cmd curl
require_cmd jq
require_cmd find

save_request() {
  local name="$1"
  local payload="$2"
  printf '%s\n' "$payload" > "$OUT_DIR/requests/${name}.json"
}

post_json() {
  local name="$1"
  local endpoint="$2"
  local payload="$3"
  save_request "$name" "$payload"
  if ! curl -sS --max-time 240 \
    -X POST "$API$endpoint" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -d "$payload" \
    > "$OUT_DIR/responses/${name}.json"; then
    jq -n --arg error "curl_failed" --arg endpoint "$endpoint" \
      '{error:$error,endpoint:$endpoint}' > "$OUT_DIR/responses/${name}.json"
  fi
}

get_json() {
  local name="$1"
  local endpoint="$2"
  if ! curl -sS --max-time 120 \
    -X GET "$API$endpoint" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    > "$OUT_DIR/responses/${name}.json"; then
    jq -n --arg error "curl_failed" --arg endpoint "$endpoint" \
      '{error:$error,endpoint:$endpoint}' > "$OUT_DIR/responses/${name}.json"
  fi
}

EMAIL="llm_eval_${TS}@example.com"
USERNAME="llm_eval_${TS}"
PASSWORD="EvalPass_123456"

REG_PAYLOAD="$(jq -n --arg email "$EMAIL" --arg username "$USERNAME" --arg password "$PASSWORD" '{email:$email,username:$username,password:$password}')"
printf '%s\n' "$REG_PAYLOAD" > "$OUT_DIR/requests/auth_register.json"

curl -sS --max-time 60 \
  -X POST "$API/auth/register" \
  -H "Content-Type: application/json" \
  -d "$REG_PAYLOAD" \
  > "$OUT_DIR/responses/auth_register.json" || true

LOGIN_PAYLOAD="$(jq -n --arg email "$EMAIL" --arg password "$PASSWORD" '{email:$email,password:$password}')"
printf '%s\n' "$LOGIN_PAYLOAD" > "$OUT_DIR/requests/auth_login.json"

curl -sS --max-time 60 \
  -X POST "$API/auth/login" \
  -H "Content-Type: application/json" \
  -d "$LOGIN_PAYLOAD" \
  > "$OUT_DIR/responses/auth_login.json"

ACCESS_TOKEN="$(jq -r '.access_token // empty' "$OUT_DIR/responses/auth_login.json")"
if [[ -z "$ACCESS_TOKEN" ]]; then
  echo "[ERROR] login failed" >&2
  cat "$OUT_DIR/responses/auth_login.json" >&2
  exit 1
fi

echo "[INFO] auth ok"

PROJECT_PAYLOAD="$(jq -n --arg name "LLM quality eval $TS" --arg description "Live run over backend/tests/test_doc PDFs" '{name:$name,description:$description}')"
printf '%s\n' "$PROJECT_PAYLOAD" > "$OUT_DIR/requests/project_create.json"

curl -sS --max-time 60 \
  -X POST "$API/projects" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -d "$PROJECT_PAYLOAD" \
  > "$OUT_DIR/responses/project_create.json"

PROJECT_ID="$(jq -r '.id // empty' "$OUT_DIR/responses/project_create.json")"
if [[ -z "$PROJECT_ID" ]]; then
  echo "[ERROR] create project failed" >&2
  cat "$OUT_DIR/responses/project_create.json" >&2
  exit 1
fi

echo "[INFO] project id: $PROJECT_ID"

PAPER_IDS=()
mkdir -p "$OUT_DIR/staged_pdfs"
mapfile -t PDF_FILES < <(find "$PDF_ROOT" -type f -name '*.pdf' | LC_ALL=C sort)

if [[ -n "$PDF_NAME_FILTER" ]]; then
  FILTERED=()
  for pdf in "${PDF_FILES[@]}"; do
    base="$(basename "$pdf")"
    if [[ "$base" == *"$PDF_NAME_FILTER"* ]]; then
      FILTERED+=("$pdf")
    fi
  done
  PDF_FILES=("${FILTERED[@]}")
fi

if [[ "$MAX_PDFS" =~ ^[0-9]+$ ]] && (( MAX_PDFS > 0 )) && (( ${#PDF_FILES[@]} > MAX_PDFS )); then
  PDF_FILES=("${PDF_FILES[@]:0:MAX_PDFS}")
fi

echo "[INFO] pdf root: $PDF_ROOT"
echo "[INFO] pdf count: ${#PDF_FILES[@]}"

if [[ ${#PDF_FILES[@]} -eq 0 ]]; then
  echo "[ERROR] no pdf files found under $PDF_ROOT" >&2
  exit 1
fi

idx=0
for pdf in "${PDF_FILES[@]}"; do
  idx=$((idx + 1))
  base="$(basename "$pdf")"
  staged_pdf="$OUT_DIR/staged_pdfs/paper_${idx}.pdf"
  cp "$pdf" "$staged_pdf"
  safe="paper_${idx}"
  curl -sS --max-time 180 \
    -X POST "$API/papers/upload?project_id=$PROJECT_ID" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -F "file=@$staged_pdf" \
    > "$OUT_DIR/responses/upload_${safe}.json"
  pid="$(jq -r '.id // empty' "$OUT_DIR/responses/upload_${safe}.json")"
  if [[ -n "$pid" ]]; then
    PAPER_IDS+=("$pid")
    echo "[INFO] uploaded $base -> paper_id=$pid"
  else
    echo "[WARN] upload failed for $base"
    cat "$OUT_DIR/responses/upload_${safe}.json"
  fi
done

if [[ ${#PAPER_IDS[@]} -eq 0 ]]; then
  echo "[ERROR] no paper uploaded" >&2
  exit 1
fi

printf '%s\n' "${PAPER_IDS[@]}" > "$OUT_DIR/paper_ids.txt"

echo "[INFO] waiting paper processing..."
DEADLINE=$((SECONDS + 600))
while true; do
  all_done=1
  list_file="$OUT_DIR/responses/papers_list_poll.json"
  if ! curl -sS --max-time 20 \
    -X GET "$API/papers?project_id=$PROJECT_ID&page_size=100" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    > "$list_file"; then
    all_done=0
    sleep 5
    continue
  fi

  for pid in "${PAPER_IDS[@]}"; do
    st="$(jq -r --argjson pid "$pid" '.items[]? | select(.id == $pid) | .status' "$list_file" 2>/dev/null | head -n1)"
    if [[ -z "$st" ]]; then
      st="missing"
    fi
    jq -n --argjson pid "$pid" --arg status "$st" \
      '{id:$pid,status:$status}' > "$OUT_DIR/responses/paper_status_${pid}.json"
    if [[ "$st" != "completed" && "$st" != "failed" ]]; then
      all_done=0
    fi
  done

  if [[ $all_done -eq 1 ]]; then
    break
  fi

  if (( SECONDS > DEADLINE )); then
    echo "[WARN] status polling timeout"
    break
  fi
  sleep 5
done

get_json "papers_list" "/papers?project_id=$PROJECT_ID&page_size=100"

# ---- RAG ----
Q1="Summarize the core modules of RAG based on papers in this project, and list the main challenge for each module."
Q2="Compare the stage taxonomy of RAG evolution in the Gao, Fan, and Gupta survey papers."
Q3="From the cybersecurity education paper in this project, describe participants, intervention design, and key outcomes."
Q4="Propose a practical short/mid/long-term improvement roadmap for a production RAG system based only on project papers."

for i in 1 2 3 4; do
  qvar="Q${i}"
  q="${!qvar}"
  payload="$(jq -n --arg question "$q" --argjson pid "$PROJECT_ID" '{question:$question,project_id:$pid,top_k:8}')"
  post_json "rag_ask_0${i}" "/rag/ask" "$payload"
done

RAG_STREAM_PAYLOAD="$(jq -n --arg question "Give a concise synthesis of all project papers and include explicit citation markers." --argjson pid "$PROJECT_ID" '{question:$question,project_id:$pid,top_k:8}')"
save_request "rag_stream_01" "$RAG_STREAM_PAYLOAD"
curl -sS -N --max-time 240 \
  -X POST "$API/rag/stream" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -d "$RAG_STREAM_PAYLOAD" \
  > "$OUT_DIR/sse/rag_stream_01.sse" || printf '%s\n' "curl_failed rag_stream_01" > "$OUT_DIR/sse/rag_stream_01.sse"

# ---- Writing APIs ----
WRITING_OUTLINE_PAYLOAD="$(jq -n --arg topic "Retrieval-Augmented Generation survey synthesis and implementation guidelines" --argjson pid "$PROJECT_ID" '{topic:$topic,project_id:$pid,style:"journal"}')"
post_json "writing_outline" "/writing/outline" "$WRITING_OUTLINE_PAYLOAD"

WRITING_REVIEW_PAYLOAD="$(jq -n --arg topic "Recent advances and open challenges in retrieval-augmented generation" --argjson pid "$PROJECT_ID" '{topic:$topic,project_id:$pid,max_words:1200,focus_areas:["retrieval architecture","evaluation","hallucination"]}')"
post_json "writing_review" "/writing/review" "$WRITING_REVIEW_PAYLOAD"

POLISH_TEXT="RAG methods are useful but many paper do not agree on architecture, and many benchmark setting are inconsistent. In addition, it is difficult to explain why retrieval help in some task but not other task."
WRITING_POLISH_PAYLOAD="$(jq -n --arg text "$POLISH_TEXT" '{text:$text,style:"academic",language:"en"}')"
post_json "writing_polish" "/writing/polish" "$WRITING_POLISH_PAYLOAD"

CITATION_TEXT="Recent survey studies indicate that retrieval quality, context compression, and citation-grounded decoding are central to robust RAG deployment in real systems."
WRITING_CITATION_PAYLOAD="$(jq -n --arg text "$CITATION_TEXT" --argjson pid "$PROJECT_ID" '{text:$text,project_id:$pid,limit:10}')"
post_json "writing_suggest_citations" "/writing/suggest-citations" "$WRITING_CITATION_PAYLOAD"

# ---- Agent APIs ----
AGENT_ASK_AUTO="$(jq -n --arg query "Compare major RAG survey viewpoints and provide an evidence-backed answer." --argjson pid "$PROJECT_ID" '{query:$query,project_id:$pid,params:{top_k:8}}')"
post_json "agent_ask_auto" "/agent/ask" "$AGENT_ASK_AUTO"

AGENT_ASK_ANALYZER="$(jq -n --arg query "Analyze trend shifts discussed in project RAG surveys and explain implications." --argjson pid "$PROJECT_ID" '{query:$query,project_id:$pid,agent_type:"analyzer_agent",params:{analysis_type:"comparison"}}')"
post_json "agent_ask_analyzer" "/agent/ask" "$AGENT_ASK_ANALYZER"

AGENT_MULTI_PAYLOAD="$(jq -n --arg query "Provide retrieval answer, analysis view, and writing suggestion for improving RAG robustness." --argjson pid "$PROJECT_ID" '{query:$query,project_id:$pid,agent_types:["retriever_agent","analyzer_agent","writer_agent"],params:{top_k:8}}')"
post_json "agent_multi" "/agent/multi" "$AGENT_MULTI_PAYLOAD"

AGENT_WRITE_OUTLINE="$(jq -n --arg query "Generate a structured paper outline for RAG system optimization." --argjson pid "$PROJECT_ID" '{query:$query,project_id:$pid,task_type:"outline"}')"
post_json "agent_write_outline" "/agent/write" "$AGENT_WRITE_OUTLINE"

AGENT_WRITE_REVIEW="$(jq -n --arg query "Write a compact literature review on RAG evolution and unresolved issues." --argjson pid "$PROJECT_ID" '{query:$query,project_id:$pid,task_type:"review"}')"
post_json "agent_write_review" "/agent/write" "$AGENT_WRITE_REVIEW"

AGENT_WRITE_POLISH="$(jq -n --arg query "Please polish this paragraph for academic style." --arg context "$POLISH_TEXT" --argjson pid "$PROJECT_ID" '{query:$query,project_id:$pid,task_type:"polish",context:$context}')"
post_json "agent_write_polish" "/agent/write" "$AGENT_WRITE_POLISH"

AGENT_WRITE_CITATION="$(jq -n --arg query "$CITATION_TEXT" --argjson pid "$PROJECT_ID" '{query:$query,project_id:$pid,task_type:"citation"}')"
post_json "agent_write_citation" "/agent/write" "$AGENT_WRITE_CITATION"

AGENT_ANALYZE_PAYLOAD="$(jq -n --arg query "Extract top keyword clusters and timeline evolution for project papers." --argjson pid "$PROJECT_ID" '{query:$query,project_id:$pid,analysis_type:"timeline"}')"
post_json "agent_analyze" "/agent/analyze" "$AGENT_ANALYZE_PAYLOAD"

AGENT_KG_PAYLOAD="$(jq -n --argjson pid "$PROJECT_ID" '{project_id:$pid,max_entities:35}')"
post_json "agent_knowledge_graph" "/agent/knowledge-graph" "$AGENT_KG_PAYLOAD"

AGENT_STREAM_PAYLOAD="$(jq -n --arg query "Synthesize all project papers into actionable guidance with cited evidence." --argjson pid "$PROJECT_ID" '{query:$query,project_id:$pid,params:{top_k:8}}')"
save_request "agent_stream_01" "$AGENT_STREAM_PAYLOAD"
curl -sS -N --max-time 300 \
  -X POST "$API/agent/stream" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -d "$AGENT_STREAM_PAYLOAD" \
  > "$OUT_DIR/sse/agent_stream_01.sse" || printf '%s\n' "curl_failed agent_stream_01" > "$OUT_DIR/sse/agent_stream_01.sse"

# ---- Memory reconstruct ----
MEMORY_RECON_TRUE="$(jq -n --arg query "Reconstruct key memory threads about RAG architecture and evaluation trade-offs." --argjson pid "$PROJECT_ID" '{query:$query,project_id:$pid,use_llm:true}')"
post_json "memory_reconstruct_llm_true" "/memory/reconstruct" "$MEMORY_RECON_TRUE"

MEMORY_RECON_FALSE="$(jq -n --arg query "Reconstruct key memory threads about RAG architecture and evaluation trade-offs." --argjson pid "$PROJECT_ID" '{query:$query,project_id:$pid,use_llm:false}')"
post_json "memory_reconstruct_llm_false" "/memory/reconstruct" "$MEMORY_RECON_FALSE"

# Conversations and memory status snapshots
get_json "rag_conversations" "/rag/conversations?project_id=$PROJECT_ID&limit=100"
get_json "rag_conversations_count" "/rag/conversations/count"
get_json "memory_stats" "/memory/stats?project_id=$PROJECT_ID"
get_json "memory_list" "/memory/list?project_id=$PROJECT_ID&limit=50"

if [[ "$CLEANUP_PROJECT" == "1" || "$CLEANUP_PROJECT" == "true" ]]; then
  echo "[INFO] cleanup project: $PROJECT_ID"
  curl -sS --max-time 60 \
    -X DELETE "$API/projects/$PROJECT_ID" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    > "$OUT_DIR/responses/project_delete.json" || true
fi

jq -n \
  --arg out_dir "$OUT_DIR" \
  --arg ts "$TS" \
  --arg email "$EMAIL" \
  --arg username "$USERNAME" \
  --argjson project_id "$PROJECT_ID" \
  --arg pdf_root "$PDF_ROOT" \
  --arg pdf_name_filter "$PDF_NAME_FILTER" \
  --argjson max_pdfs "${MAX_PDFS:-0}" \
  --arg cleanup_project "$CLEANUP_PROJECT" \
  --argjson paper_ids "$(printf '%s\n' "${PAPER_IDS[@]}" | jq -R . | jq -s 'map(tonumber)')" \
  '{timestamp:$ts,out_dir:$out_dir,test_user:{email:$email,username:$username},project_id:$project_id,paper_ids:$paper_ids,pdf_root:$pdf_root,pdf_name_filter:$pdf_name_filter,max_pdfs:$max_pdfs,cleanup_project:$cleanup_project}' \
  > "$OUT_DIR/run_meta.json"

echo "[DONE] live eval completed"
echo "$OUT_DIR"
