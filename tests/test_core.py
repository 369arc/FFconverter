"""Unit tests for the non-GUI parts of FFConverter.

Run with: python3 -m unittest discover -s tests -v
No X display is required because no Tk root is created.
"""

import tempfile
import unittest
from pathlib import Path

import ffc


class Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class BaseAppTest(unittest.TestCase):
    def make_app(self):
        app = object.__new__(ffc.FFConverterApp)
        app.video_format = Var("MP4")
        app.video_quality_mode = Var("ORIGINAL (COPY)")
        app.video_quality_value = Var("1080P (5M)")
        app.video_remove_audio = Var(False)
        app.video_remove_video = Var(False)
        app.video_deinterlace = Var(False)
        app.video_frame_rate = Var("ORIGINAL (COPY)")
        app.video_keep_aspect_ratio = Var(True)

        app.audio_format = Var("MP3")
        app.audio_quality = Var("192K")
        app.audio_dithering = Var(False)
        app.audio_limiter = Var(False)
        app.mp3_mode = Var("CBR")

        app.image_format = Var("JPG")
        app.image_size = Var("ORIGINAL (COPY)")
        app.custom_image_dims = None
        app.image_keep_aspect_ratio = Var(True)
        app.image_visual_filter = Var("ORIGINAL (NO FILTER)")
        app.image_compress = Var(False)
        return app


class HelperTests(unittest.TestCase):
    def test_unique_output_path_avoids_collisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            reserved = set()
            first = ffc.unique_output_path(directory, "clip", "MP4", reserved)
            second = ffc.unique_output_path(directory, "clip", "mp4", reserved)
            self.assertEqual(first.name, "clip_converted.mp4")
            self.assertEqual(second.name, "clip_converted_1.mp4")
            self.assertNotEqual(first, second)

    def test_unique_output_path_skips_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "clip_converted.mp4").write_text("x")
            path = ffc.unique_output_path(directory, "clip", "mp4")
            self.assertEqual(path.name, "clip_converted_1.mp4")

    def test_parse_progress(self):
        self.assertAlmostEqual(
            ffc.parse_ffmpeg_progress("out_time_us=1500000")["seconds"], 1.5
        )
        self.assertEqual(
            ffc.parse_ffmpeg_progress("progress=end")["progress"], "end"
        )
        self.assertEqual(ffc.parse_ffmpeg_progress("not a key/value line"), {})

    def test_tab_for_path(self):
        self.assertEqual(ffc.tab_for_path("movie.MTS"), "Video")
        self.assertEqual(ffc.tab_for_path("song.flac"), "Audio")
        self.assertEqual(ffc.tab_for_path("photo.PNG"), "Image")
        self.assertIsNone(ffc.tab_for_path("notes.txt"))


class VideoArgsTests(BaseAppTest):
    def test_copy_mode(self):
        app = self.make_app()
        cmd = []
        self.assertEqual(app._build_video_args(cmd), "mp4")
        self.assertIn("copy", cmd)
        self.assertIn("-movflags", cmd)

    def test_copy_mode_rejects_filters(self):
        app = self.make_app()
        app.video_deinterlace = Var(True)
        with self.assertRaises(ValueError):
            app._build_video_args([])

    def test_bitrate_preset_scales_to_resolution(self):
        app = self.make_app()
        app.video_quality_mode = Var("BITRATE (CBR/VBR AVG)")
        app.video_quality_value = Var("1080P (5M)")
        cmd = []
        app._build_video_args(cmd)
        self.assertIn("scale=-2:1080", cmd)
        self.assertIn("5M", cmd)
        self.assertIn("aac", cmd)

    def test_crf_for_x264(self):
        app = self.make_app()
        app.video_quality_mode = Var("CRF (CONSTANT QUALITY)")
        app.video_quality_value = Var("23 (GOOD - DEFAULT)")
        cmd = []
        app._build_video_args(cmd)
        self.assertIn("-crf", cmd)
        self.assertIn("23", cmd)
        self.assertIn("-preset", cmd)

    def test_crf_is_not_passed_to_mpeg1(self):
        app = self.make_app()
        app.video_format = Var("MPG")
        app.video_quality_mode = Var("CRF (CONSTANT QUALITY)")
        app.video_quality_value = Var("23 (GOOD - DEFAULT)")
        cmd = []
        app._build_video_args(cmd)
        self.assertNotIn("-crf", cmd)
        self.assertIn("-q:v", cmd)

    def test_remove_video_extracts_wav(self):
        app = self.make_app()
        app.video_remove_video = Var(True)
        cmd = []
        self.assertEqual(app._build_video_args(cmd), "wav")
        self.assertIn("pcm_s16le", cmd)
        self.assertNotIn("copy", cmd)


class AudioArgsTests(BaseAppTest):
    def test_wav_with_filter_uses_pcm_not_aac(self):
        app = self.make_app()
        app.audio_format = Var("WAV")
        app.audio_quality = Var("48000 HZ")
        app.audio_limiter = Var(True)
        cmd = []
        self.assertEqual(app._build_audio_args(cmd), "wav")
        self.assertIn("pcm_s16le", cmd)
        self.assertNotIn("aac", cmd)
        self.assertIn("-ar", cmd)

    def test_alac_uses_m4a_container(self):
        app = self.make_app()
        app.audio_format = Var("ALAC")
        app.audio_quality = Var("44100 HZ")
        cmd = []
        self.assertEqual(app._build_audio_args(cmd), "m4a")
        self.assertIn("alac", cmd)

    def test_amr_forces_8khz_mono(self):
        app = self.make_app()
        app.audio_format = Var("AMR")
        app.audio_quality = Var("12.2K")
        cmd = []
        app._build_audio_args(cmd)
        self.assertIn("8000", cmd)
        self.assertIn("-ac", cmd)

    def test_mp3_vbr(self):
        app = self.make_app()
        app.mp3_mode = Var("VBR")
        app.audio_quality = Var("V2 (HIGH QUALITY)")
        cmd = []
        app._build_audio_args(cmd)
        self.assertIn("-q:a", cmd)
        self.assertIn("2", cmd)

    def test_ogg_cli_does_not_offer_broken_320k(self):
        self.assertNotIn("320K", ffc.AUDIO_SETTINGS["OGG"]["options"])


class ImageArgsTests(BaseAppTest):
    def test_jpeg_compress_is_applied(self):
        app = self.make_app()
        app.image_compress = Var(True)
        cmd = []
        self.assertEqual(app._build_image_args(cmd), "jpg")
        self.assertIn("-q:v", cmd)

    def test_resize_keeps_ratio_with_even_dimensions(self):
        app = self.make_app()
        app.image_size = Var("1280X720 (HD)")
        cmd = []
        app._build_image_args(cmd)
        self.assertIn("scale=1280:-2", cmd)

    def test_ico_is_limited_to_256(self):
        app = self.make_app()
        app.image_format = Var("ICO")
        cmd = []
        app._build_image_args(cmd)
        self.assertIn("scale=256:256:force_original_aspect_ratio=decrease", cmd)

    def test_animated_png_gets_single_frame(self):
        app = self.make_app()
        cmd = []
        app._build_image_args(cmd)
        self.assertIn("-frames:v", cmd)


class ValidationTests(BaseAppTest):
    def test_mts_is_valid_video_input(self):
        app = self.make_app()
        valid, rejected = app._validate_files(["/tmp/camera.MTS"], "Video")
        self.assertEqual(valid, ["/tmp/camera.MTS"])
        self.assertEqual(rejected, [])

    def test_psd_is_valid_image_input(self):
        app = self.make_app()
        valid, rejected = app._validate_files(["/tmp/scan.psd"], "Image")
        self.assertEqual(valid, ["/tmp/scan.psd"])
        self.assertEqual(rejected, [])

    def test_unknown_extension_is_rejected(self):
        app = self.make_app()
        valid, rejected = app._validate_files(["/tmp/notes.txt"], "Video")
        self.assertEqual(valid, [])
        self.assertEqual(rejected, ["/tmp/notes.txt"])


if __name__ == "__main__":
    unittest.main()
