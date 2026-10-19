# Changelog

## 1.1.0 — 2026-10-19

### 新增

- 5 种钢琴音色：音乐会三角 `grand`、明亮流行 `bright`、毛毡柔音 `felt`、复古立式 `upright`、
  梦幻电钢 `electric`。顶栏可直接切换，切换后保留播放进度。
- 命令行 `--voice` 选项，用于指定启动音色。
- 每种音色独立缓存，缓存指纹加入音色名。

### 改进

- 重写合成器：泛音按各自频率非谐性与衰减时间演化，加入双弦失谐、锤击噪声、力度亮度与声像，
  听感更接近真实钢琴。
- 截图脚本支持 `--voice`，并修正了等待渲染时阻塞渲染线程的问题。

### 修复

- 修复 Windows 免安装版没有声音的问题：冻结包内 `soundfile` 触发
  `ImportError: DLL load failed while importing _ctypes`，导致合成失败后回退为静音。
  现在改用 Python 标准库 `wave` 写出 WAV，不再依赖 `soundfile`。
- `piano-waterfall --help` 现在正常打印帮助并退出，不再误启动窗口。

## 1.0.0

- 首个版本：MIDI 解析、离线钢琴合成、瀑布流动画、5 套主题、播放控制、全屏、
  可选的 AI 音频转 MIDI、Windows 免安装包与 GitHub Actions。
