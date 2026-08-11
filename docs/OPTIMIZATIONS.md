# AvatarLive 调优与实测心得

本文记录基于 SoulX-FlashHead 流式引擎在真实 GPU 环境（RTX 4090）上反复实测得到的经验，用于换形象、调口型、降延迟、排查问题。

## 1. 形象（参考图）选择 —— 决定一切

FlashHead 用一张参考图（`cond_image_path`）作为数字人的脸。**这张图直接决定：长相、眼睛方向、以及待机时嘴的闭合程度**。

| 维度 | 最佳做法 | 原因 |
|---|---|---|
| 脸部 | 正脸、居中、完整入镜 | 生成稳定，不歪脸 |
| 眼睛 | **睁眼、平视前方** | 参考图闭眼 → 输出全程闭眼（扩散模型忠实复现参考图） |
| 嘴巴 | **闭合** | 参考图张嘴 → 待机（静音）时嘴也张着。**待机嘴型基线 = 参考图的嘴型** |
| 分辨率 | 大于 512×512 会被自动 resize；直接给 512×512 最省事 | 管线按 `infer_params.yaml` 的 512×512 处理 |
| 表情 | 中性、无大表情 | 参考图表情会被「传染」到所有生成帧 |

**换形象**：`POST /api/avatar` 上传图片即可热换，无需重启。详见 README。

> 挑帧小工具思路：从一段真人视频里找「正脸 + 睁眼 + 嘴闭合」的一帧当参考图。用手动逐帧预览挑选即可（正脸优先，其次嘴闭合）。

## 2. 眼睛稳定 —— sample_shift

`src/handlers/avatar/flashhead/SoulX-FlashHead/flash_head/configs/infer_params.yaml` 里的 `sample_shift` 控制生成时的时序采样偏移：

- 默认 `5` → 眼睛略飘/眨眼频率偏高
- **`8`（本仓库默认）** → 眼睛明显更稳定，减少「斗鸡眼」感
- 不建议超过 10，画面会变僵

## 3. 口型：幅度预期与关键参数

**预期**：FlashHead 是扩散模型，口型动态幅度天然比「音视频对口型」方案小。这是特性不是 bug —— 它更像真人自然说话，而不是唱歌式的夸张嘴型。

实测数据（嘴部暗区垂直跨距 / 脸高）：
- 待机（静音）：≈ 3%（嘴闭合）
- 说话中：≈ 3-7%
- 说话→待机过渡：偶发 ≤ 4.6%（已修复，见下）

**关键参数**：

| 参数 | 默认 | 说明 |
|---|---|---|
| `idle_noise_amplitude: 0.0` | 0.0 | 待机音频用纯静音，保证待机嘴闭合。**注意：真正的待机基线由参考图决定，光设这个不够** |
| `paste_back: false` | false | 512×512 脸占满画面；`true` 时把生成的脸贴回全帧背景（v3 构图），脸占画面 ~37% |
| `use_face_crop: false` | false | 关闭前置人脸裁剪（FlashHead 自带的 mediapipe 依赖已惰性化，开裁剪才需要装 mediapipe） |

**响度不影响口型**：wav2vec2 音频特征内部做了幅度归一化，把 TTS 音频调大/调小对张嘴幅度基本无效，不要在这上面浪费时间。

## 4. 说话→待机「残留大嘴」修复（重要）

流式管线在静音时**忠实复现参考图嘴型**。早期版本在语音播完后，音频滑动窗口（deque）残留了语音尾巴、运动 latent 停在说话状态，导致待机偶发张嘴 15%。

修复已在 `flashhead_processor.py` 的 `add_audio` end_of_speech 分支：
```
音频 deque 重置为 8s 静音 + _latent_motion_frames 重置为 _initial_latent_1slice
```
实测修复后：连续 4 次捕获，说话 max ≤ 4.6%、待机 max 3.8%，无尖峰。

## 5. 实时 vs 批量的区别（为什么"嘴上"数字不一样）

官方 `generate_video.py` 是**批量**管线（整段音频一次生成）；OAC/AvatarLive 是**流式**管线（分块推理 + 待机微动 + 打断）。两者：

- 同一张参考图、同一份 `infer_params`、同一模型权重 → 生成基础一致
- 但流式多了「待机静音段」「说话→待机过渡」，嘴型统计会不同。**对比时要用同一管线模式**，别拿流式待机和批量说话帧比

## 6. 延迟预算（RTX 4090 实测）

| 阶段 | 耗时 |
|---|---|
| FlashHead Lite 模型加载（冷启动） | ~9s（首帧才真正推理，浏览器首连略等） |
| ASR（SenseVoice） | 0.1-0.9s |
| LLM（mock 回声 / API） | ~0.02s / 数百 ms |
| edge-tts 合成 | **2-6s（微软在线，最大瓶颈）** |
| FlashHead 触发→首说话帧 | 0.6-0.9s |
| FlashHead 推理 | 44-67 FPS（2× 实时健康） |

端到端（说话→开口）≈ 3.5-7s，瓶颈在在线 TTS。需要更低延迟就把 TTS 换成本地方案（CosyVoice 规划中）。

## 7. 打断与复位

- 说话中发新语音 → 自动打断当前，从头说新的
- 双工模式（`*_duplex*.yaml`）支持边说边打断
- 打断后 processor 会清空音频缓冲并复位 latent，回到闭合待机

## 8. 常见问题排查

| 现象 | 排查 |
|---|---|
| 浏览器连不上 / ICE 一直 checking | 公网必须配 TURN（`RtcClient.turn_config`），纯 TCP 网络用 `?transport=tcp`；UDP 3478 不转发时只走 TCP TURN |
| 数字人不出现 | 浏览器需摄像头+麦克风权限；`createDataChannel` 必须建立（客户端要发数据通道才会起会话） |
| 待机嘴张着 | 换一张嘴闭合的参考图（第 1 节） |
| 换形象后没生效 | 确认 `/api/avatar` 返回 200；已连会话需重新加载页面重连（或等下一帧自动用新脸） |
| 冷启动很久 | torch.compile 已禁用（Blackwell 兼容）；加载 ~9s 属正常 |
| mediapipe 报错 | 只有 `use_face_crop: true` 才需要 mediapipe，默认不装也能跑 |

## 9. 上传超长语音 → 口型错位（帧积压 backlog）

**现象**：`POST /api/speak` 上传一段较长音频（实测 **69 秒**），数字人口型和声音对不上（嘴动时刻与声音错位）。

**根因**（pod 日志 `oac_run.log` 实测定量）：
- `broadcast_speak` 把**整段音频一次性全量** `add_audio(..., end=True)` 喂给 FlashHead。
- FlashHead 是流式引擎：每次只推理 `slice_len=24 帧`（≈1 秒语音），推理速度 **57-68 FPS**（正常，不是推理慢）。
- 但**产出端（推理 60FPS）≫ 消费端（RTC 视频轨固定 25FPS）**，帧在 `_output_queue` 越积越多，日志出现 `FlashHead TIMING: frame queue_wait 60→81 秒 (backlog)`。
- 客户端先播队列里最早的帧，音频轨却按自己的时钟走 → 音画错位。

**关键对比**：5.4s 音频 ≈ 135 帧，无积压，口型正常；69s 音频 ≈ 1725 帧，积压暴涨到 81 秒。**时长超过约 15-20 秒后积压明显**。

**结论**：不是语速快、不是推理慢，而是**一次性注入超长音频**导致的队列积压。

**已知的解决方向（未实施）**：
- **A（根治，推荐）**：改 `broadcast_speak` 为**流式喂入**——把音频按 ~1 秒切片多次 `add_audio(end=False)`，最后一片 `end=True`，让推理跟着消费节奏走，避免积压。改动集中在 `src/handlers/avatar/flashhead/avatar_handler_flashhead.py` 的 `broadcast_speak`。
- **B（治标）**：前端/文档提示「单段音频建议 ≤ 15 秒」。

**复现/验证**：pod 上 `resource/test/sample_speech_16k.wav`（5.4s）正常；上传 60s+ 音频可见 `queue_wait` 持续增长。自测脚本 `/tmp/upload_audio_test.py`。
