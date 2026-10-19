# hFT-Transformer transcription model

`hft_transformer.onnx` is an ONNX export of the official hFT-Transformer
checkpoint released by Sony CSL.

- Upstream project: https://github.com/sony/hFT-Transformer
- Paper: Qiuqiang Kong, Bochen Li, Xuchen Song, Yuan Wan, Yuxuan Wang.
  "High-Resolution Piano Transcription with Pedals by Regressing Onset and
  Offset Times." IEEE/ACM TASLP, 2021.
- License: MIT (see the upstream repository)
- Export: the official PyTorch checkpoint was converted to ONNX (opset 17,
  dynamic batch dimension, fixed 256-bin log-mel input with 192 frames per
  window). The network weights are unchanged; only the serialization format
  differs.

The model is used for offline audio-to-MIDI transcription inside Piano
Waterfall. It runs locally on the CPU through ONNX Runtime; no audio is
uploaded anywhere.
