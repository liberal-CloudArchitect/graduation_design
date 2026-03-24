Last login: Fri Mar 20 00:21:54 on ttys010
╭─duckduke@DuckdukedeMacBook-Pro ~ ‹main●› 
╰─$ ssh "desktop-6h5ff1j\robin"@192.168.50.173
desktop-6h5ff1j\robin@192.168.50.173's password: 

Microsoft Windows [版本 10.0.26200.7840]
(c) Microsoft Corporation。保留所有权利。

robin@DESKTOP-6H5FF1J C:\Users\Robin>cd /d E:\project\graduation_design-main

robin@DESKTOP-6H5FF1J E:\project\graduation_design-main>cd mineru_service

robin@DESKTOP-6H5FF1J E:\project\graduation_design-main\mineru_service>docker build -t mineru-service:latest .
[+] Building 21.3s (2/2) FINISHED                                                                                                          docker:desktop-linux
 => [internal] load build definition from Dockerfile                                                                                                       0.1s
 => => transferring dockerfile: 1.85kB                                                                                                                     0.0s
 => ERROR [internal] load metadata for docker.io/vllm/vllm-openai:v0.10.1.1                                                                               21.1s
------
 > [internal] load metadata for docker.io/vllm/vllm-openai:v0.10.1.1:
------
Dockerfile:17
--------------------
  15 |     # Tested on: RTX 4060 Laptop (8GB VRAM, Driver 572.16, Windows Docker Desktop)
  16 |     # --------------------------------------------------------------------------
  17 | >>> FROM vllm/vllm-openai:v0.10.1.1
  18 |     
  19 |     # System deps: PDF/image libs, CJK fonts
--------------------
ERROR: failed to build: failed to solve: vllm/vllm-openai:v0.10.1.1: failed to resolve source metadata for docker.io/vllm/vllm-openai:v0.10.1.1: failed to do request: Head "https://registry-1.docker.io/v2/vllm/vllm-openai/manifests/v0.10.1.1": dialing registry-1.docker.io:443 container via direct connection because Docker Desktop has no HTTPS proxy: connecting to registry-1.docker.io:443: dial tcp 199.59.148.6:443: connectex: A connection attempt failed because the connected party did not properly respond after a period of time, or established connection failed because connected host has failed to respond.

robin@DESKTOP-6H5FF1J E:\project\graduation_design-main\mineru_service>docker pull vllm/vllm-openai:v0.10.1.1
error getting credentials - err: exit status 1, out: `A specified logon session does not exist. It may already have been terminated.`

robin@DESKTOP-6H5FF1J E:\project\graduation_design-main\mineru_service>docker build -t mineru-service:latest .
[+] Building 21.2s (2/2) FINISHED                                                                                                          docker:desktop-linux
 => [internal] load build definition from Dockerfile                                                                                                       0.0s
 => => transferring dockerfile: 1.85kB                                                                                                                     0.0s
 => ERROR [internal] load metadata for docker.io/vllm/vllm-openai:v0.10.1.1                                                                               21.0s
------
 > [internal] load metadata for docker.io/vllm/vllm-openai:v0.10.1.1:
------
Dockerfile:17
--------------------
  15 |     # Tested on: RTX 4060 Laptop (8GB VRAM, Driver 572.16, Windows Docker Desktop)
  16 |     # --------------------------------------------------------------------------
  17 | >>> FROM vllm/vllm-openai:v0.10.1.1
  18 |     
  19 |     # System deps: PDF/image libs, CJK fonts
--------------------
ERROR: failed to build: failed to solve: vllm/vllm-openai:v0.10.1.1: failed to resolve source metadata for docker.io/vllm/vllm-openai:v0.10.1.1: failed to do request: Head "https://registry-1.docker.io/v2/vllm/vllm-openai/manifests/v0.10.1.1": dialing registry-1.docker.io:443 container via direct connection because Docker Desktop has no HTTPS proxy: connecting to registry-1.docker.io:443: dial tcp 199.59.148.6:443: connectex: A connection attempt failed because the connected party did not properly respond after a period of time, or established connection failed because connected host has failed to respond.

robin@DESKTOP-6H5FF1J E:\project\graduation_design-main\mineru_service>Read from remote host 192.168.50.173: No route to host
Connection to 192.168.50.173 closed.
client_loop: send disconnect: Broken pipe
╭─duckduke@DuckdukedeMacBook-Pro ~ ‹main●› 
╰─$ ssh "desktop-6h5ff1j\robin"@192.168.50.173                                                                                                              25
desktop-6h5ff1j\robin@192.168.50.173's password: 

Microsoft Windows [版本 10.0.26200.7840]
(c) Microsoft Corporation。保留所有权利。

robin@DESKTOP-6H5FF1J C:\Users\Robin>cd /d E:\project\graduation_design-main

robin@DESKTOP-6H5FF1J E:\project\graduation_design-main>cd mineru_service

robin@DESKTOP-6H5FF1J E:\project\graduation_design-main\mineru_service>docker logs -f mineru-service
[entrypoint] Starting MinerU OpenAI server (gpu-memory-utilization=0.25, port=30000)...
[entrypoint] Waiting for vLLM server to become healthy (timeout=180s)...
2026-03-19 11:13:03.046 | INFO     | mineru.cli.vlm_server:openai_server:33 - Using vLLM as the inference engine for VLM server.
INFO 03-19 11:13:08 [__init__.py:241] Automatically detected platform cuda.
2026-03-19 11:13:11.580 | INFO     | mineru.backend.vlm.utils:enable_custom_logits_processors:55 - compute_capability: 8.9 >= 8.0 and vllm version: 0.10.1.1 >= 0.10.1, enable custom_logits_processors
start vllm server: ['/usr/local/bin/mineru-openai-server', 'serve', '/root/.cache/huggingface/hub/models--opendatalab--MinerU2.5-2509-1.2B/snapshots/879e58bdd9566632b27a8a81f0e2961873311f67', '--host', '127.0.0.1', '--port', '30000', '--gpu-memory-utilization', '0.25', '--logits-processors', 'mineru_vl_utils:MinerULogitsProcessor']
(APIServer pid=7) INFO 03-19 11:13:12 [api_server.py:1805] vLLM API server version 0.10.1.1
(APIServer pid=7) INFO 03-19 11:13:12 [utils.py:326] non-default args: {'model_tag': '/root/.cache/huggingface/hub/models--opendatalab--MinerU2.5-2509-1.2B/snapshots/879e58bdd9566632b27a8a81f0e2961873311f67', 'host': '127.0.0.1', 'port': 30000, 'model': '/root/.cache/huggingface/hub/models--opendatalab--MinerU2.5-2509-1.2B/snapshots/879e58bdd9566632b27a8a81f0e2961873311f67', 'logits_processors': ['mineru_vl_utils:MinerULogitsProcessor'], 'gpu_memory_utilization': 0.25}
(APIServer pid=7) INFO 03-19 11:13:17 [__init__.py:711] Resolved architecture: Qwen2VLForConditionalGeneration
(APIServer pid=7) INFO 03-19 11:13:17 [__init__.py:1750] Using max model len 16384
(APIServer pid=7) INFO 03-19 11:13:17 [scheduler.py:222] Chunked prefill is enabled with max_num_batched_tokens=2048.
(APIServer pid=7) WARNING 03-19 11:13:17 [cache.py:216] Possibly too large swap space. 4.00 GiB out of the 7.63 GiB total CPU memory is allocated for the swap space.
INFO 03-19 11:13:21 [__init__.py:241] Automatically detected platform cuda.
(EngineCore_0 pid=62) INFO 03-19 11:13:21 [core.py:636] Waiting for init message from front-end.
(EngineCore_0 pid=62) INFO 03-19 11:13:21 [core.py:74] Initializing a V1 LLM engine (v0.10.1.1) with config: model='/root/.cache/huggingface/hub/models--opendatalab--MinerU2.5-2509-1.2B/snapshots/879e58bdd9566632b27a8a81f0e2961873311f67', speculative_config=None, tokenizer='/root/.cache/huggingface/hub/models--opendatalab--MinerU2.5-2509-1.2B/snapshots/879e58bdd9566632b27a8a81f0e2961873311f67', skip_tokenizer_init=False, tokenizer_mode=auto, revision=None, override_neuron_config={}, tokenizer_revision=None, trust_remote_code=False, dtype=torch.bfloat16, max_seq_len=16384, download_dir=None, load_format=auto, tensor_parallel_size=1, pipeline_parallel_size=1, disable_custom_all_reduce=False, quantization=None, enforce_eager=False, kv_cache_dtype=auto, device_config=cuda, decoding_config=DecodingConfig(backend='auto', disable_fallback=False, disable_any_whitespace=False, disable_additional_properties=False, reasoning_backend=''), observability_config=ObservabilityConfig(show_hidden_metrics_for_version=None, otlp_traces_endpoint=None, collect_detailed_traces=None), seed=0, served_model_name=/root/.cache/huggingface/hub/models--opendatalab--MinerU2.5-2509-1.2B/snapshots/879e58bdd9566632b27a8a81f0e2961873311f67, enable_prefix_caching=True, chunked_prefill_enabled=True, use_async_output_proc=True, pooler_config=None, compilation_config={"level":3,"debug_dump_path":"","cache_dir":"","backend":"","custom_ops":[],"splitting_ops":["vllm.unified_attention","vllm.unified_attention_with_output","vllm.mamba_mixer2"],"use_inductor":true,"compile_sizes":[],"inductor_compile_config":{"enable_auto_functionalized_v2":false},"inductor_passes":{},"cudagraph_mode":1,"use_cudagraph":true,"cudagraph_num_of_warmups":1,"cudagraph_capture_sizes":[512,504,496,488,480,472,464,456,448,440,432,424,416,408,400,392,384,376,368,360,352,344,336,328,320,312,304,296,288,280,272,264,256,248,240,232,224,216,208,200,192,184,176,168,160,152,144,136,128,120,112,104,96,88,80,72,64,56,48,40,32,24,16,8,4,2,1],"cudagraph_copy_inputs":false,"full_cuda_graph":false,"pass_config":{},"max_capture_size":512,"local_cache_dir":null}
(EngineCore_0 pid=62) INFO 03-19 11:13:24 [parallel_state.py:1134] rank 0 in world size 1 is assigned as DP rank 0, PP rank 0, TP rank 0, EP rank 0
(EngineCore_0 pid=62) WARNING 03-19 11:13:24 [interface.py:389] Using 'pin_memory=False' as WSL is detected. This may slow down the performance.
(EngineCore_0 pid=62) INFO 03-19 11:13:24 [topk_topp_sampler.py:50] Using FlashInfer for top-p & top-k sampling.
(EngineCore_0 pid=62) INFO 03-19 11:13:25 [gpu_model_runner.py:1953] Starting to load model /root/.cache/huggingface/hub/models--opendatalab--MinerU2.5-2509-1.2B/snapshots/879e58bdd9566632b27a8a81f0e2961873311f67...
(EngineCore_0 pid=62) INFO 03-19 11:13:26 [gpu_model_runner.py:1985] Loading model from scratch...
(EngineCore_0 pid=62) WARNING 03-19 11:13:26 [cuda.py:211] Current `vllm-flash-attn` has a bug inside vision module, so we use xformers backend instead. You can run `pip install flash-attn` to use flash-attention backend.
(EngineCore_0 pid=62) WARNING 03-19 11:13:26 [cache.py:216] Possibly too large swap space. 4.00 GiB out of the 7.63 GiB total CPU memory is allocated for the swap space.
(EngineCore_0 pid=62) INFO 03-19 11:13:26 [cuda.py:328] Using Flash Attention backend on V1 engine.
Loading safetensors checkpoint shards:   0% Completed | 0/1 [00:00<?, ?it/s]
Loading safetensors checkpoint shards: 100% Completed | 1/1 [00:01<00:00,  1.79s/it]
Loading safetensors checkpoint shards: 100% Completed | 1/1 [00:01<00:00,  1.79s/it]
(EngineCore_0 pid=62)
(EngineCore_0 pid=62) INFO 03-19 11:13:28 [default_loader.py:262] Loading weights took 1.85 seconds
(EngineCore_0 pid=62) INFO 03-19 11:13:28 [gpu_model_runner.py:2007] Model loading took 2.1641 GiB and 2.091096 seconds
(EngineCore_0 pid=62) INFO 03-19 11:13:28 [gpu_model_runner.py:2591] Encoder cache will be initialized with a budget of 14175 tokens, and profiled with 1 video items of the maximum feature size.
(EngineCore_0 pid=62) INFO 03-19 11:13:33 [backends.py:548] Using cache directory: /root/.cache/vllm/torch_compile_cache/b90351217d/rank_0_0/backbone for vLLM's torch.compile
(EngineCore_0 pid=62) INFO 03-19 11:13:33 [backends.py:559] Dynamo bytecode transform time: 2.51 s
(EngineCore_0 pid=62) INFO 03-19 11:13:35 [backends.py:194] Cache the graph for dynamic shape for later use
(EngineCore_0 pid=62) [rank0]:W0319 11:13:36.095000 62 torch/_inductor/utils.py:1250] [0/0] Not enough SMs to use max_autotune_gemm mode
(EngineCore_0 pid=62) INFO 03-19 11:13:46 [backends.py:215] Compiling a graph for dynamic shape takes 12.46 s
(EngineCore_0 pid=62) INFO 03-19 11:13:55 [monitor.py:34] torch.compile takes 14.97 s in total
(EngineCore_0 pid=62) /usr/local/lib/python3.12/dist-packages/torch/utils/cpp_extension.py:2356: UserWarning: TORCH_CUDA_ARCH_LIST is not set, all archs for visible cards are included for compilation.
(EngineCore_0 pid=62) If this is not desired, please set os.environ['TORCH_CUDA_ARCH_LIST'].
(EngineCore_0 pid=62)   warnings.warn(
(EngineCore_0 pid=62) INFO 03-19 11:14:31 [gpu_worker.py:276] Available KV cache memory: -0.72 GiB
(EngineCore_0 pid=62) Process EngineCore_0:
(EngineCore_0 pid=62) ERROR 03-19 11:14:31 [core.py:700] EngineCore failed to start.
(EngineCore_0 pid=62) ERROR 03-19 11:14:31 [core.py:700] Traceback (most recent call last):
(EngineCore_0 pid=62) ERROR 03-19 11:14:31 [core.py:700]   File "/usr/local/lib/python3.12/dist-packages/vllm/v1/engine/core.py", line 691, in run_engine_core    
(EngineCore_0 pid=62) ERROR 03-19 11:14:31 [core.py:700]     engine_core = EngineCoreProc(*args, **kwargs)
(EngineCore_0 pid=62) ERROR 03-19 11:14:31 [core.py:700]                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
(EngineCore_0 pid=62) ERROR 03-19 11:14:31 [core.py:700]   File "/usr/local/lib/python3.12/dist-packages/vllm/v1/engine/core.py", line 492, in __init__
(EngineCore_0 pid=62) ERROR 03-19 11:14:31 [core.py:700]     super().__init__(vllm_config, executor_class, log_stats,
(EngineCore_0 pid=62) ERROR 03-19 11:14:31 [core.py:700]   File "/usr/local/lib/python3.12/dist-packages/vllm/v1/engine/core.py", line 89, in __init__
(EngineCore_0 pid=62) ERROR 03-19 11:14:31 [core.py:700]     self._initialize_kv_caches(vllm_config)
(EngineCore_0 pid=62) ERROR 03-19 11:14:31 [core.py:700]   File "/usr/local/lib/python3.12/dist-packages/vllm/v1/engine/core.py", line 189, in _initialize_kv_caches
(EngineCore_0 pid=62) ERROR 03-19 11:14:31 [core.py:700]     get_kv_cache_config(vllm_config, kv_cache_spec_one_worker,
(EngineCore_0 pid=62) ERROR 03-19 11:14:31 [core.py:700]   File "/usr/local/lib/python3.12/dist-packages/vllm/v1/core/kv_cache_utils.py", line 1095, in get_kv_cache_config
(EngineCore_0 pid=62) ERROR 03-19 11:14:31 [core.py:700]     check_enough_kv_cache_memory(vllm_config, kv_cache_spec, available_memory)
(EngineCore_0 pid=62) ERROR 03-19 11:14:31 [core.py:700]   File "/usr/local/lib/python3.12/dist-packages/vllm/v1/core/kv_cache_utils.py", line 682, in check_enough_kv_cache_memory
(EngineCore_0 pid=62) ERROR 03-19 11:14:31 [core.py:700]     raise ValueError("No available memory for the cache blocks. "
(EngineCore_0 pid=62) ERROR 03-19 11:14:31 [core.py:700] ValueError: No available memory for the cache blocks. Try increasing `gpu_memory_utilization` when initializing the engine.
(EngineCore_0 pid=62) Traceback (most recent call last):
(EngineCore_0 pid=62)   File "/usr/lib/python3.12/multiprocessing/process.py", line 314, in _bootstrap
(EngineCore_0 pid=62)     self.run()
(EngineCore_0 pid=62)   File "/usr/lib/python3.12/multiprocessing/process.py", line 108, in run
(EngineCore_0 pid=62)     self._target(*self._args, **self._kwargs)
(EngineCore_0 pid=62)   File "/usr/local/lib/python3.12/dist-packages/vllm/v1/engine/core.py", line 704, in run_engine_core
(EngineCore_0 pid=62)     raise e
(EngineCore_0 pid=62)   File "/usr/local/lib/python3.12/dist-packages/vllm/v1/engine/core.py", line 691, in run_engine_core
(EngineCore_0 pid=62)     engine_core = EngineCoreProc(*args, **kwargs)
(EngineCore_0 pid=62)                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
(EngineCore_0 pid=62)   File "/usr/local/lib/python3.12/dist-packages/vllm/v1/engine/core.py", line 492, in __init__
(EngineCore_0 pid=62)     super().__init__(vllm_config, executor_class, log_stats,
(EngineCore_0 pid=62)   File "/usr/local/lib/python3.12/dist-packages/vllm/v1/engine/core.py", line 89, in __init__
(EngineCore_0 pid=62)     self._initialize_kv_caches(vllm_config)
(EngineCore_0 pid=62)   File "/usr/local/lib/python3.12/dist-packages/vllm/v1/engine/core.py", line 189, in _initialize_kv_caches
(EngineCore_0 pid=62)     get_kv_cache_config(vllm_config, kv_cache_spec_one_worker,
(EngineCore_0 pid=62)   File "/usr/local/lib/python3.12/dist-packages/vllm/v1/core/kv_cache_utils.py", line 1095, in get_kv_cache_config
(EngineCore_0 pid=62)     check_enough_kv_cache_memory(vllm_config, kv_cache_spec, available_memory)
(EngineCore_0 pid=62)   File "/usr/local/lib/python3.12/dist-packages/vllm/v1/core/kv_cache_utils.py", line 682, in check_enough_kv_cache_memory
(EngineCore_0 pid=62)     raise ValueError("No available memory for the cache blocks. "
(EngineCore_0 pid=62) ValueError: No available memory for the cache blocks. Try increasing `gpu_memory_utilization` when initializing the engine.
[rank0]:[W319 11:14:32.382431904 ProcessGroupNCCL.cpp:1479] Warning: WARNING: destroy_process_group() was not called before program exit, which can leak resources. For more info, please see https://pytorch.org/docs/stable/distributed.html#shutdown (function operator())
(APIServer pid=7) Traceback (most recent call last):
(APIServer pid=7)   File "/usr/local/bin/mineru-openai-server", line 7, in <module>
(APIServer pid=7)     sys.exit(openai_server())
(APIServer pid=7)              ^^^^^^^^^^^^^^^
(APIServer pid=7)   File "/usr/local/lib/python3.12/dist-packages/click/core.py", line 1442, in __call__
(APIServer pid=7)     return self.main(*args, **kwargs)
(APIServer pid=7)            ^^^^^^^^^^^^^^^^^^^^^^^^^^
(APIServer pid=7)   File "/usr/local/lib/python3.12/dist-packages/click/core.py", line 1363, in main
(APIServer pid=7)     rv = self.invoke(ctx)
(APIServer pid=7)          ^^^^^^^^^^^^^^^^
(APIServer pid=7)   File "/usr/local/lib/python3.12/dist-packages/click/core.py", line 1226, in invoke
(APIServer pid=7)     return ctx.invoke(self.callback, **ctx.params)
(APIServer pid=7)            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
(APIServer pid=7)   File "/usr/local/lib/python3.12/dist-packages/click/core.py", line 794, in invoke
(APIServer pid=7)     return callback(*args, **kwargs)
(APIServer pid=7)            ^^^^^^^^^^^^^^^^^^^^^^^^^
(APIServer pid=7)   File "/usr/local/lib/python3.12/dist-packages/click/decorators.py", line 34, in new_func
(APIServer pid=7)     return f(get_current_context(), *args, **kwargs)
(APIServer pid=7)            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
(APIServer pid=7)   File "/usr/local/lib/python3.12/dist-packages/mineru/cli/vlm_server.py", line 51, in openai_server
(APIServer pid=7)     vllm_server()
(APIServer pid=7)   File "/usr/local/lib/python3.12/dist-packages/mineru/cli/vlm_server.py", line 9, in vllm_server
(APIServer pid=7)     main()
(APIServer pid=7)   File "/usr/local/lib/python3.12/dist-packages/vllm/entrypoints/openai/api_server.py", line 1850, in run_server
(APIServer pid=7)     await run_server_worker(listen_address, sock, args, **uvicorn_kwargs)
(APIServer pid=7)   File "/usr/local/lib/python3.12/dist-packages/vllm/entrypoints/openai/api_server.py", line 1870, in run_server_worker
(APIServer pid=7)     async with build_async_engine_client(
(APIServer pid=7)                ^^^^^^^^^^^^^^^^^^^^^^^^^^
(APIServer pid=7)   File "/usr/lib/python3.12/contextlib.py", line 210, in __aenter__
(APIServer pid=7)     return await anext(self.gen)
(APIServer pid=7)            ^^^^^^^^^^^^^^^^^^^^^
(APIServer pid=7)   File "/usr/local/lib/python3.12/dist-packages/vllm/entrypoints/openai/api_server.py", line 178, in build_async_engine_client
(APIServer pid=7)     async with build_async_engine_client_from_engine_args(
(APIServer pid=7)                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
(APIServer pid=7)   File "/usr/lib/python3.12/contextlib.py", line 210, in __aenter__
(APIServer pid=7)     return await anext(self.gen)
(APIServer pid=7)            ^^^^^^^^^^^^^^^^^^^^^
(APIServer pid=7)   File "/usr/local/lib/python3.12/dist-packages/vllm/entrypoints/openai/api_server.py", line 220, in build_async_engine_client_from_engine_args 
(APIServer pid=7)     async_llm = AsyncLLM.from_vllm_config(
(APIServer pid=7)                 ^^^^^^^^^^^^^^^^^^^^^^^^^^
(APIServer pid=7)   File "/usr/local/lib/python3.12/dist-packages/vllm/utils/__init__.py", line 1557, in inner
(APIServer pid=7)     return fn(*args, **kwargs)
(APIServer pid=7)            ^^^^^^^^^^^^^^^^^^^
(APIServer pid=7)   File "/usr/local/lib/python3.12/dist-packages/vllm/v1/engine/async_llm.py", line 174, in from_vllm_config
(APIServer pid=7)     return cls(
(APIServer pid=7)            ^^^^
(APIServer pid=7)   File "/usr/local/lib/python3.12/dist-packages/vllm/v1/engine/async_llm.py", line 120, in __init__
(APIServer pid=7)     self.engine_core = EngineCoreClient.make_async_mp_client(
(APIServer pid=7)                        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
(APIServer pid=7)   File "/usr/local/lib/python3.12/dist-packages/vllm/v1/engine/core_client.py", line 102, in make_async_mp_client
(APIServer pid=7)     return AsyncMPClient(*client_args)
(APIServer pid=7)            ^^^^^^^^^^^^^^^^^^^^^^^^^^^
(APIServer pid=7)   File "/usr/local/lib/python3.12/dist-packages/vllm/v1/engine/core_client.py", line 767, in __init__
(APIServer pid=7)     super().__init__(
(APIServer pid=7)   File "/usr/local/lib/python3.12/dist-packages/vllm/v1/engine/core_client.py", line 446, in __init__
(APIServer pid=7)     with launch_core_engines(vllm_config, executor_class,
(APIServer pid=7)          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
(APIServer pid=7)   File "/usr/lib/python3.12/contextlib.py", line 144, in __exit__
(APIServer pid=7)     next(self.gen)
(APIServer pid=7)   File "/usr/local/lib/python3.12/dist-packages/vllm/v1/engine/utils.py", line 706, in launch_core_engines
(APIServer pid=7)     wait_for_engine_startup(
(APIServer pid=7)   File "/usr/local/lib/python3.12/dist-packages/vllm/v1/engine/utils.py", line 759, in wait_for_engine_startup
(APIServer pid=7)     raise RuntimeError("Engine core initialization failed. "
(APIServer pid=7) RuntimeError: Engine core initialization failed. See root cause above. Failed core proc(s): {}
[entrypoint] ERROR: vLLM server process exited unexpectedly
[entrypoint] Falling back to pipeline-only mode
INFO:     Started server process [1]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8010 (Press CTRL+C to quit)
