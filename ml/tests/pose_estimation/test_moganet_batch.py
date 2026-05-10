"""Tests for MogaNet batch inference module."""

import numpy as np
import pytest

from src.pose_estimation.moganet_batch import (
    MOGANET_INPUT_SIZE,
    MogaNetBatch,
    decode_heatmaps,
    preprocess_crops,
    rescale_keypoints,
)


class TestPreprocessCrops:
    def test_output_shape(self):
        """Verify output is (B, 3, 288, 384) float32."""
        crops = [np.random.randint(0, 255, (200, 150, 3), dtype=np.uint8) for _ in range(4)]
        tensor = preprocess_crops(crops)
        assert tensor.shape == (4, 3, MOGANET_INPUT_SIZE[1], MOGANET_INPUT_SIZE[0])
        assert tensor.dtype == np.float32
        assert len(tensor) == 4

    def test_single_crop(self):
        """Single crop yields batch_size=1."""
        crop = np.random.randint(0, 255, (200, 150, 3), dtype=np.uint8)
        tensor = preprocess_crops([crop])
        assert tensor.shape[0] == 1

    def test_bgr_to_rgb(self):
        """BGR blue channel becomes RGB blue (channel index 2 in CHW)."""
        crop = np.zeros((50, 50, 3), dtype=np.uint8)
        crop[:, :, 0] = 255  # Blue channel in BGR
        tensor = preprocess_crops([crop])
        # After BGR->RGB, the original BGR blue ends up in RGB blue (CHW channel 2)
        # The crop is scaled and centered: 50x50 -> scale=5.76 -> 288x288, pad_left=48
        # Crop content region in CHW: channels=all, height=0:288, width=48:336
        # Pixel (0, 0) in content = tensor[0, 2, 0, 48] should be RGB blue (value ~2.64)
        assert tensor[0, 2, 0, 48] > 2.0, f"Expected >2.0, got {tensor[0, 2, 0, 48]}"

    def test_normalization_applied(self):
        """Verify ImageNet mean/std normalization is applied."""
        crop = np.full((50, 50, 3), 128, dtype=np.uint8)
        tensor = preprocess_crops([crop])
        # 50x50 -> scale=5.76 -> new_h=288, new_w=288, pad_left=(384-288)/2=48
        # Content pixel at tensor[0, 0, 0, 48] should be normalized
        # (128/255 - 0.485) / 0.229
        expected = ((128.0 / 255.0) - 0.485) / 0.229
        assert tensor[0, 0, 0, 48] == pytest.approx(expected, abs=0.02)

    def test_letterbox_preserves_aspect_ratio(self):
        """Tall crop should be letterboxed (padded left/right)."""
        # Very tall crop: 400x100 (HxW), so aspect ratio constrained by height
        crop = np.random.randint(0, 255, (400, 100, 3), dtype=np.uint8)
        tensor = preprocess_crops([crop])
        # scale = min(384/100, 288/400) = min(3.84, 0.72) = 0.72
        # new_h = 400 * 0.72 = 288, new_w = 100 * 0.72 = 72
        # pad_left = (384 - 72) / 2 = 156
        # Check that left padding area is normalized 0-value
        # 0 normalized in R: (0 - 0.485) / 0.229 approx -2.12
        left_pad = tensor[0, 0, :, :156].mean()
        right_start = 384 - 156
        right_pad = tensor[0, 0, :, right_start:].mean()
        assert left_pad == pytest.approx(-2.12, abs=0.1)
        assert right_pad == pytest.approx(-2.12, abs=0.1)

    def test_empty_crops(self):
        """Empty list returns empty tensor."""
        tensor = preprocess_crops([])
        assert tensor.shape == (0, 3, MOGANET_INPUT_SIZE[1], MOGANET_INPUT_SIZE[0])


class TestDecodeHeatmaps:
    def test_single_peak_per_joint(self):
        """Single clear peak per joint, verify correct coordinate scaling."""
        batch_size = 2
        num_joints = 17
        heatmap_h, heatmap_w = 72, 96

        heatmaps = np.zeros((batch_size, num_joints, heatmap_h, heatmap_w), dtype=np.float32)
        for b in range(batch_size):
            for j in range(num_joints):
                y_peak = (j * 4 + 5) % heatmap_h
                x_peak = (j * 7 + 3) % heatmap_w
                heatmaps[b, j, y_peak, x_peak] = 1.0

        keypoints, scores = decode_heatmaps(heatmaps)

        assert keypoints.shape == (batch_size, num_joints, 2)
        assert scores.shape == (batch_size, num_joints)

        for b in range(batch_size):
            for j in range(num_joints):
                y_peak = (j * 4 + 5) % heatmap_h
                x_peak = (j * 7 + 3) % heatmap_w
                # Scale from heatmap to model input space
                expected_x = x_peak * MOGANET_INPUT_SIZE[0] / heatmap_w
                expected_y = y_peak * MOGANET_INPUT_SIZE[1] / heatmap_h
                assert keypoints[b, j, 0] == pytest.approx(expected_x, abs=0.5)
                assert keypoints[b, j, 1] == pytest.approx(expected_y, abs=0.5)
                assert scores[b, j] == pytest.approx(1.0)

    def test_no_peaks(self):
        """All-zero heatmaps produce near-zero scores."""
        heatmaps = np.zeros((1, 17, 72, 96), dtype=np.float32)
        _keypoints, scores = decode_heatmaps(heatmaps)
        assert np.all(scores < 0.01)


class TestRescaleKeypoints:
    def test_no_letterbox_no_offset(self):
        """Crop exactly matches input size, bbox at origin: no change."""
        crop = np.random.randint(0, 255, (288, 384, 3), dtype=np.uint8)
        keypoints = np.full((1, 17, 2), 100.0, dtype=np.float32)
        keypoints[0, 0] = [100.0, 200.0]
        bboxes = [(0, 0, 384, 288)]
        rescaled = rescale_keypoints(keypoints, [crop], bboxes)
        assert rescaled.shape == (1, 17, 2)
        # Scale = 1.0, no padding, bbox at origin -> same coords
        assert rescaled[0, 0, 0] == pytest.approx(100.0)
        assert rescaled[0, 0, 1] == pytest.approx(200.0)

    def test_with_bbox_offset(self):
        """Bbox origin offset is added to keypoints."""
        crop = np.random.randint(0, 255, (200, 150, 3), dtype=np.uint8)
        keypoints = np.array([[50.0, 75.0]] * 17, dtype=np.float32).reshape(1, 17, 2)
        bboxes = [(100, 50, 150, 200)]

        # Compute expected rescaling
        input_w, input_h = 384, 288
        crop_h, crop_w = 200, 150
        scale = min(input_w / crop_w, input_h / crop_h)
        new_w = int(crop_w * scale)
        new_h = int(crop_h * scale)
        pad_left = (input_w - new_w) / 2
        pad_top = (input_h - new_h) / 2

        expected_x = (50.0 - pad_left) / scale + 100.0
        expected_y = (75.0 - pad_top) / scale + 50.0

        rescaled = rescale_keypoints(keypoints, [crop], bboxes)
        assert rescaled[0, 0, 0] == pytest.approx(expected_x, abs=0.5)
        assert rescaled[0, 0, 1] == pytest.approx(expected_y, abs=0.5)

    def test_multiple_crops(self):
        """Different crops and bboxes handled correctly."""
        crops = [
            np.random.randint(0, 255, (288, 384, 3), dtype=np.uint8),
            np.random.randint(0, 255, (200, 150, 3), dtype=np.uint8),
        ]
        keypoints = np.zeros((2, 17, 2), dtype=np.float32)
        keypoints[0, :] = [100.0, 150.0]
        keypoints[1, :] = [50.0, 75.0]
        bboxes = [(0, 0, 384, 288), (100, 50, 150, 200)]

        rescaled = rescale_keypoints(keypoints, crops, bboxes)

        # First crop: no letterbox, no offset
        assert rescaled[0, 0, 0] == pytest.approx(100.0)
        assert rescaled[0, 0, 1] == pytest.approx(150.0)

        # Second crop: letterbox + offset
        crop_h, crop_w = 200, 150
        scale = min(384 / crop_w, 288 / crop_h)
        new_w = int(crop_w * scale)
        new_h = int(crop_h * scale)
        pad_left = (384 - new_w) / 2
        pad_top = (288 - new_h) / 2
        expected_x = (50.0 - pad_left) / scale + 100.0
        expected_y = (75.0 - pad_top) / scale + 50.0
        assert rescaled[1, 0, 0] == pytest.approx(expected_x, abs=0.5)
        assert rescaled[1, 0, 1] == pytest.approx(expected_y, abs=0.5)


class TestMogaNetBatchInit:
    def test_init_without_model_raises(self):
        """Missing model file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            MogaNetBatch(model_path="/nonexistent/model.onnx", device="cpu")

    def test_init_auto_device_cuda_available(self, monkeypatch, tmp_path):
        """Auto device selects cuda when CUDAExecutionProvider is available."""
        model_path = tmp_path / "model.onnx"
        model_path.write_bytes(b"fake")

        mock_ort = _make_mock_onnxruntime(cuda_available=True)
        monkeypatch.setitem(__import__("sys").modules, "onnxruntime", mock_ort)

        batch = MogaNetBatch(model_path=str(model_path), device="auto")
        assert batch._device == "cuda"
        batch.close()

    def test_init_auto_device_cpu_fallback(self, monkeypatch, tmp_path):
        """Auto device falls back to cpu when CUDA is not available."""
        model_path = tmp_path / "model.onnx"
        model_path.write_bytes(b"fake")

        mock_ort = _make_mock_onnxruntime(cuda_available=False)
        monkeypatch.setitem(__import__("sys").modules, "onnxruntime", mock_ort)

        batch = MogaNetBatch(model_path=str(model_path), device="auto")
        assert batch._device == "cpu"
        batch.close()

    def test_init_auto_device_onnxruntime_import_error(self, monkeypatch, tmp_path):
        """Auto device falls back to cpu when onnxruntime cannot be imported."""
        model_path = tmp_path / "model.onnx"
        model_path.write_bytes(b"fake")

        # First import (device resolution) fails, second (session creation) succeeds
        import_count = 0
        orig_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

        def fake_import(name, *args, **kwargs):
            nonlocal import_count
            if name == "onnxruntime":
                import_count += 1
                if import_count == 1:
                    raise ImportError("onnxruntime not available")
                return _make_mock_onnxruntime(cuda_available=False)
            return orig_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", fake_import)

        batch = MogaNetBatch(model_path=str(model_path), device="auto")
        assert batch._device == "cpu"
        batch.close()

    def test_init_loads_onnx_session(self, monkeypatch, tmp_path):
        """Init creates ONNX session with correct providers and runs warm-up."""
        model_path = tmp_path / "model.onnx"
        model_path.write_bytes(b"fake")

        mock_ort = _make_mock_onnxruntime(cuda_available=False)
        monkeypatch.setitem(__import__("sys").modules, "onnxruntime", mock_ort)

        batch = MogaNetBatch(model_path=str(model_path), device="cpu")
        session = batch._session

        # Verify session was created with CPU provider
        assert session._providers_used == ["CPUExecutionProvider"]
        # Verify warm-up was called (run called once during init)
        assert session._run_count >= 1
        # Verify input/output names stored
        assert batch._input_name == "input"
        assert batch._output_names == ["output"]
        batch.close()

    def test_init_cuda_providers(self, monkeypatch, tmp_path):
        """Init with cuda device uses CUDA + CPU providers."""
        model_path = tmp_path / "model.onnx"
        model_path.write_bytes(b"fake")

        mock_ort = _make_mock_onnxruntime(cuda_available=True)
        monkeypatch.setitem(__import__("sys").modules, "onnxruntime", mock_ort)

        batch = MogaNetBatch(model_path=str(model_path), device="cuda")
        assert batch._session._providers_used == [
            "CUDAExecutionProvider",
            "CPUExecutionProvider",
        ]
        batch.close()


class TestMogaNetBatchInferBatch:
    def test_infer_batch_empty_crops(self, monkeypatch, tmp_path):
        """infer_batch with empty crops returns empty arrays."""
        model_path = tmp_path / "model.onnx"
        model_path.write_bytes(b"fake")

        mock_ort = _make_mock_onnxruntime()
        monkeypatch.setitem(__import__("sys").modules, "onnxruntime", mock_ort)

        batch = MogaNetBatch(model_path=str(model_path), device="cpu")
        keypoints, scores = batch.infer_batch([], [])
        assert keypoints.shape == (0, 17, 2)
        assert scores.shape == (0, 17)
        batch.close()

    def test_infer_batch_mismatched_lengths_raises(self, monkeypatch, tmp_path):
        """infer_batch raises ValueError when crops and bboxes have different lengths."""
        model_path = tmp_path / "model.onnx"
        model_path.write_bytes(b"fake")

        mock_ort = _make_mock_onnxruntime()
        monkeypatch.setitem(__import__("sys").modules, "onnxruntime", mock_ort)

        batch = MogaNetBatch(model_path=str(model_path), device="cpu")
        crops = [np.zeros((100, 100, 3), dtype=np.uint8)]
        bboxes = [(0, 0, 100, 100), (0, 0, 50, 50)]  # 2 bboxes for 1 crop

        with pytest.raises(ValueError, match="crops and bboxes must have same length"):
            batch.infer_batch(crops, bboxes)
        batch.close()

    def test_infer_batch_single_crop(self, monkeypatch, tmp_path):
        """infer_batch processes a single crop and returns correct shapes."""
        model_path = tmp_path / "model.onnx"
        model_path.write_bytes(b"fake")

        mock_ort = _make_mock_onnxruntime()
        monkeypatch.setitem(__import__("sys").modules, "onnxruntime", mock_ort)

        batch = MogaNetBatch(model_path=str(model_path), device="cpu")
        crop = np.zeros((200, 150, 3), dtype=np.uint8)
        bbox = (10, 20, 140, 180)

        keypoints, scores = batch.infer_batch([crop], [bbox])
        assert keypoints.shape == (1, 17, 2)
        assert scores.shape == (1, 17)
        batch.close()

    def test_infer_batch_multiple_crops(self, monkeypatch, tmp_path):
        """infer_batch processes multiple crops and concatenates results."""
        model_path = tmp_path / "model.onnx"
        model_path.write_bytes(b"fake")

        mock_ort = _make_mock_onnxruntime()
        monkeypatch.setitem(__import__("sys").modules, "onnxruntime", mock_ort)

        batch = MogaNetBatch(model_path=str(model_path), device="cpu")
        crops = [
            np.zeros((200, 150, 3), dtype=np.uint8),
            np.zeros((300, 200, 3), dtype=np.uint8),
        ]
        bboxes = [(10, 20, 140, 180), (30, 40, 200, 280)]

        keypoints, scores = batch.infer_batch(crops, bboxes)
        assert keypoints.shape == (2, 17, 2)
        assert scores.shape == (2, 17)
        batch.close()

    def test_infer_batch_score_threshold_applied(self, monkeypatch, tmp_path):
        """infer_batch zeros out scores below the threshold."""
        model_path = tmp_path / "model.onnx"
        model_path.write_bytes(b"fake")

        # Create mock that returns heatmaps with known max values (some below threshold)
        mock_ort = _make_mock_onnxruntime(heatmap_max=0.1)
        monkeypatch.setitem(__import__("sys").modules, "onnxruntime", mock_ort)

        batch = MogaNetBatch(model_path=str(model_path), device="cpu", score_thr=0.3)
        crop = np.zeros((200, 150, 3), dtype=np.uint8)
        bbox = (10, 20, 140, 180)

        _keypoints, scores = batch.infer_batch([crop], [bbox])
        # All scores should be 0 since heatmap max (0.1) < score_thr (0.3)
        assert np.all(scores == 0.0)
        batch.close()

    def test_infer_batch_chunked_inference(self, monkeypatch, tmp_path):
        """infer_batch processes more than _MAX_GPU_BATCH items in chunks."""
        model_path = tmp_path / "model.onnx"
        model_path.write_bytes(b"fake")

        mock_ort = _make_mock_onnxruntime()
        monkeypatch.setitem(__import__("sys").modules, "onnxruntime", mock_ort)

        batch = MogaNetBatch(model_path=str(model_path), device="cpu")
        # Create more crops than _MAX_GPU_BATCH (32)
        n = 35
        crops = [np.zeros((100, 80, 3), dtype=np.uint8) for _ in range(n)]
        bboxes = [(0, 0, 80, 100) for _ in range(n)]

        keypoints, scores = batch.infer_batch(crops, bboxes)
        assert keypoints.shape == (n, 17, 2)
        assert scores.shape == (n, 17)
        # Session.run should have been called multiple times (chunks)
        assert batch._session._run_count >= 2  # At least 2 chunks: 32 + 3
        batch.close()

    def test_infer_batch_preserves_original_scores(self, monkeypatch, tmp_path):
        """Score thresholding does not mutate the raw scores array."""
        model_path = tmp_path / "model.onnx"
        model_path.write_bytes(b"fake")

        mock_ort = _make_mock_onnxruntime(heatmap_max=0.5)
        monkeypatch.setitem(__import__("sys").modules, "onnxruntime", mock_ort)

        batch = MogaNetBatch(model_path=str(model_path), device="cpu", score_thr=0.3)
        crop = np.zeros((200, 150, 3), dtype=np.uint8)
        bbox = (10, 20, 140, 180)

        _keypoints, scores = batch.infer_batch([crop], [bbox])
        # With heatmap_max=0.5 and threshold=0.3, scores should NOT be zeroed
        assert np.all(scores > 0.0)
        batch.close()


class TestMogaNetBatchLifecycle:
    def test_close_deletes_session(self, monkeypatch, tmp_path):
        """close() removes the _session attribute."""
        model_path = tmp_path / "model.onnx"
        model_path.write_bytes(b"fake")

        mock_ort = _make_mock_onnxruntime()
        monkeypatch.setitem(__import__("sys").modules, "onnxruntime", mock_ort)

        batch = MogaNetBatch(model_path=str(model_path), device="cpu")
        assert hasattr(batch, "_session")
        batch.close()
        assert not hasattr(batch, "_session")

    def test_close_idempotent(self, monkeypatch, tmp_path):
        """close() can be called multiple times without error."""
        model_path = tmp_path / "model.onnx"
        model_path.write_bytes(b"fake")

        mock_ort = _make_mock_onnxruntime()
        monkeypatch.setitem(__import__("sys").modules, "onnxruntime", mock_ort)

        batch = MogaNetBatch(model_path=str(model_path), device="cpu")
        batch.close()
        batch.close()  # Should not raise

    def test_context_manager_enter_returns_self(self, monkeypatch, tmp_path):
        """__enter__ returns the MogaNetBatch instance."""
        model_path = tmp_path / "model.onnx"
        model_path.write_bytes(b"fake")

        mock_ort = _make_mock_onnxruntime()
        monkeypatch.setitem(__import__("sys").modules, "onnxruntime", mock_ort)

        with MogaNetBatch(model_path=str(model_path), device="cpu") as batch:
            assert isinstance(batch, MogaNetBatch)
            assert hasattr(batch, "_session")

    def test_context_manager_exit_closes_session(self, monkeypatch, tmp_path):
        """__exit__ calls close() and releases session."""
        model_path = tmp_path / "model.onnx"
        model_path.write_bytes(b"fake")

        mock_ort = _make_mock_onnxruntime()
        monkeypatch.setitem(__import__("sys").modules, "onnxruntime", mock_ort)

        batch = MogaNetBatch(model_path=str(model_path), device="cpu")
        batch.__exit__(None, None, None)
        assert not hasattr(batch, "_session")

    def test_context_manager_full_flow(self, monkeypatch, tmp_path):
        """Context manager allows inference inside with block, then closes."""
        model_path = tmp_path / "model.onnx"
        model_path.write_bytes(b"fake")

        mock_ort = _make_mock_onnxruntime()
        monkeypatch.setitem(__import__("sys").modules, "onnxruntime", mock_ort)

        with MogaNetBatch(model_path=str(model_path), device="cpu") as batch:
            crop = np.zeros((100, 80, 3), dtype=np.uint8)
            kp, _sc = batch.infer_batch([crop], [(0, 0, 80, 100)])
            assert kp.shape == (1, 17, 2)
        # After with block, session should be cleaned up
        assert not hasattr(batch, "_session")


# --- Helper to create mock onnxruntime module ---


def _make_mock_onnxruntime(cuda_available: bool = False, heatmap_max: float = 1.0):
    """Create a mock onnxruntime module with a fake InferenceSession.

    Args:
        cuda_available: Whether CUDAExecutionProvider is reported as available.
        heatmap_max: Max value for the fake heatmap output (controls score values).
    """

    class FakeSessionOptions:
        graph_optimization_level = None
        enable_mem_pattern = False
        enable_mem_reuse = False
        intra_op_num_threads = 1
        inter_op_num_threads = 1

    class FakeGraphOptimizationLevel:
        ORT_ENABLE_ALL = "ORT_ENABLE_ALL"

    class FakeInferenceSession:
        def __init__(self, model_path, sess_options=None, providers=None):
            self._providers_used = providers or []
            self._run_count = 0
            self._heatmap_max = heatmap_max

        def get_inputs(self):
            return [type("Input", (), {"name": "input"})()]

        def get_outputs(self):
            return [type("Output", (), {"name": "output"})()]

        def run(self, output_names, feed):
            self._run_count += 1
            batch_size = feed["input"].shape[0]
            # Fake heatmaps: (B, 17, 72, 96) with known max value
            heatmaps = np.full((batch_size, 17, 72, 96), self._heatmap_max, dtype=np.float32)
            return [heatmaps]

    class FakeOnnxRuntime:
        SessionOptions = FakeSessionOptions
        GraphOptimizationLevel = FakeGraphOptimizationLevel
        InferenceSession = FakeInferenceSession

        @staticmethod
        def get_available_providers():
            if cuda_available:
                return ["CUDAExecutionProvider", "CPUExecutionProvider"]
            return ["CPUExecutionProvider"]

    return FakeOnnxRuntime()
