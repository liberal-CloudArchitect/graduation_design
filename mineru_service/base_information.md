PS E:\project\graduation_design-main\mineru_service> nvidia-smi
Mon Mar  9 13:51:58 2026
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 552.22                 Driver Version: 552.22         CUDA Version: 12.4     |
|-----------------------------------------+------------------------+----------------------+
| GPU  Name                     TCC/WDDM  | Bus-Id          Disp.A | Volatile Uncorr. ECC |
| Fan  Temp   Perf          Pwr:Usage/Cap |           Memory-Usage | GPU-Util  Compute M. |
|                                         |                        |               MIG M. |
|=========================================+========================+======================|
|   0  NVIDIA GeForce RTX 4060 ...  WDDM  |   00000000:01:00.0  On |                  N/A |
| N/A   39C    P8              3W /  100W |     543MiB /   8188MiB |      0%      Default |
|                                         |                        |                  N/A |
+-----------------------------------------+------------------------+----------------------+

+-----------------------------------------------------------------------------------------+
| Processes:                                                                              |
|  GPU   GI   CI        PID   Type   Process name                              GPU Memory |
|        ID   ID                                                               Usage      |
|=========================================================================================|
|    0   N/A  N/A      2672    C+G   ...siveControlPanel\SystemSettings.exe      N/A      |
|    0   N/A  N/A     10312    C+G   C:\Windows\explorer.exe                     N/A      |
|    0   N/A  N/A     10892    C+G   ...\Docker\frontend\Docker Desktop.exe      N/A      |
|    0   N/A  N/A     11096    C+G   E:\LocalSend\localsend_app.exe              N/A      |
|    0   N/A  N/A     12104    C+G   C:\Windows\System32\ShellHost.exe           N/A      |
|    0   N/A  N/A     12392    C+G   ...nt.CBS_cw5n1h2txyewy\SearchHost.exe      N/A      |
|    0   N/A  N/A     12400    C+G   ...2txyewy\StartMenuExperienceHost.exe      N/A      |
|    0   N/A  N/A     13052    C+G   ...__8wekyb3d8bbwe\WindowsTerminal.exe      N/A      |
|    0   N/A  N/A     14212    C+G   ...on\145.0.3800.97\msedgewebview2.exe      N/A      |
|    0   N/A  N/A     14248    C+G   ...t.LockApp_cw5n1h2txyewy\LockApp.exe      N/A      |
|    0   N/A  N/A     16156    C+G   ...n\NVIDIA App\CEF\NVIDIA Overlay.exe      N/A      |
|    0   N/A  N/A     17124    C+G   ...n\NVIDIA App\CEF\NVIDIA Overlay.exe      N/A      |
|    0   N/A  N/A     18596    C+G   ...ekyb3d8bbwe\PhoneExperienceHost.exe      N/A      |
|    0   N/A  N/A     18836    C+G   ...CBS_cw5n1h2txyewy\TextInputHost.exe      N/A      |
|    0   N/A  N/A     20056    C+G   ...5225\office6\promecefpluginhost.exe      N/A      |
|    0   N/A  N/A     20948    C+G   ...64__v826wp6bftszj\TranslucentTB.exe      N/A      |
|    0   N/A  N/A     22616    C+G   ...s\System32\ApplicationFrameHost.exe      N/A      |
|    0   N/A  N/A     22928    C+G   E:\Microsoft VS Code\Code.exe               N/A      |
+-----------------------------------------------------------------------------------------+

PS E:\project\graduation_design-main\mineru_service> docker --version
Docker version 29.2.1, build a5c7197

PS E:\project\graduation_design-main\mineru_service> docker run --rm --gpus all nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04 nvidia-smi
Unable to find image 'nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04' locally
12.1.1-cudnn8-runtime-ubuntu22.04: Pulling from nvidia/cuda
e5474331d9b0: Pull complete
04fc8a31fa53: Pull complete
a14a8a8a6ebc: Pull complete
8bd2762ffdd9: Pull complete
aece8493d397: Pull complete
7d61afc7a3ac: Pull complete
2a5ee6fadd42: Pull complete
dd4939a04761: Pull complete
b0d7cc89b769: Pull complete
1532d9024b9c: Pull complete
Digest: sha256:f4d8e1264366940438f0353da6f289c7bef069d993d111f8106086ccd18c4a30
Status: Downloaded newer image for nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

==========
== CUDA ==
==========

CUDA Version 12.1.1

Container image Copyright (c) 2016-2023, NVIDIA CORPORATION & AFFILIATES. All rights reserved.

This container image and its contents are governed by the NVIDIA Deep Learning Container License.
By pulling and using the container, you accept the terms and conditions of this license:
https://developer.nvidia.com/ngc/nvidia-deep-learning-container-license

A copy of this license is made available in this container at /NGC-DL-CONTAINER-LICENSE for your convenience.

Mon Mar  9 06:03:14 2026
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 550.76.01              Driver Version: 552.22         CUDA Version: 12.4     |
|-----------------------------------------+------------------------+----------------------+
| GPU  Name                 Persistence-M | Bus-Id          Disp.A | Volatile Uncorr. ECC |
| Fan  Temp   Perf          Pwr:Usage/Cap |           Memory-Usage | GPU-Util  Compute M. |
|                                         |                        |               MIG M. |
|=========================================+========================+======================|
|   0  NVIDIA GeForce RTX 4060 ...    On  |   00000000:01:00.0  On |                  N/A |
| N/A   47C    P8              4W /  100W |     529MiB /   8188MiB |      1%      Default |
|                                         |                        |                  N/A |
+-----------------------------------------+------------------------+----------------------+

+-----------------------------------------------------------------------------------------+
| Processes:                                                                              |
|  GPU   GI   CI        PID   Type   Process name                              GPU Memory |
|        ID   ID                                                               Usage      |
|=========================================================================================|
|  No running processes found                                                             |
+-----------------------------------------------------------------------------------------+

PS E:\project\graduation_design-main\mineru_service> Get-WmiObject Win32_OperatingSystem | Select-Object TotalVisibleMemorySize, FreePhysicalMemory

TotalVisibleMemorySize FreePhysicalMemory
---------------------- ------------------
              16509076            8013364