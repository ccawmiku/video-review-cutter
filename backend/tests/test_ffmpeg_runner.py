"""Tests for FFmpeg runner abstraction and command construction."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.models.clip import ClipSegment
from app.services.ffmpeg_runner import (
    FFmpegCommandBuilder,
    MockFFmpegRunner,
    render_segments_pipeline,
)


def test_command_builder_single_segment_stream_copy(tmp_path: Path) -> None:
    """Validate FFmpeg single-segment stream copy command generation."""
    builder = FFmpegCommandBuilder(ffmpeg_path="ffmpeg")
    input_file = tmp_path / "source.mp4"
    output_file = tmp_path / "output.mp4"

    cmd = builder.build_stream_copy_single_segment(
        input_path=input_file,
        start_seconds=10.5,
        end_seconds=25.0,
        output_path=output_file,
    )

    assert cmd[0] == "ffmpeg"
    assert "-y" in cmd
    assert "-ss" in cmd
    assert "10.500" in cmd
    assert "-to" in cmd
    assert "25.000" in cmd
    assert "-i" in cmd
    assert str(input_file) in cmd
    assert "-c" in cmd
    assert "copy" in cmd
    assert cmd[-1] == str(output_file)


def test_command_builder_single_segment_reencode(tmp_path: Path) -> None:
    """Validate FFmpeg single-segment re-encode command generation (H.264/AAC)."""
    builder = FFmpegCommandBuilder(ffmpeg_path="ffmpeg")
    input_file = tmp_path / "source.mp4"
    output_file = tmp_path / "output.mp4"

    # With audio
    cmd_audio = builder.build_reencode_single_segment(
        input_path=input_file,
        start_seconds=0.0,
        end_seconds=15.2,
        output_path=output_file,
        has_audio=True,
    )
    assert "-c:v" in cmd_audio
    assert "libx264" in cmd_audio
    assert "-c:a" in cmd_audio
    assert "aac" in cmd_audio
    assert cmd_audio[-1] == str(output_file)

    # Without audio
    cmd_no_audio = builder.build_reencode_single_segment(
        input_path=input_file,
        start_seconds=0.0,
        end_seconds=15.2,
        output_path=output_file,
        has_audio=False,
    )
    assert "-an" in cmd_no_audio
    assert "-c:a" not in cmd_no_audio


def test_command_builder_multi_segment_concat_copy(tmp_path: Path) -> None:
    """Validate FFmpeg stream-copy chunk and concat demuxer command generation."""
    builder = FFmpegCommandBuilder(ffmpeg_path="ffmpeg")
    input_file = tmp_path / "source.mp4"
    chunk_file = tmp_path / "chunk_0000.mp4"
    manifest_file = tmp_path / "concat.txt"
    output_file = tmp_path / "output.mp4"

    # Chunk command
    chunk_cmd = builder.build_stream_copy_chunk(
        input_path=input_file,
        start_seconds=5.0,
        end_seconds=12.0,
        chunk_path=chunk_file,
    )
    assert "-avoid_negative_ts" in chunk_cmd
    assert "make_zero" in chunk_cmd
    assert chunk_cmd[-1] == str(chunk_file)

    # Concat demuxer command
    concat_cmd = builder.build_concat_demuxer(
        manifest_path=manifest_file,
        output_path=output_file,
        copy_streams=True,
    )
    assert "-f" in concat_cmd
    assert "concat" in concat_cmd
    assert "-safe" in concat_cmd
    assert "0" in concat_cmd
    assert "-c" in concat_cmd
    assert "copy" in concat_cmd
    assert concat_cmd[-1] == str(output_file)


def test_command_builder_multi_segment_filter_complex_reencode(tmp_path: Path) -> None:
    """Validate filter_complex re-encode command construction for multiple segments."""
    builder = FFmpegCommandBuilder(ffmpeg_path="ffmpeg")
    input_file = tmp_path / "source.mp4"
    output_file = tmp_path / "output.mp4"

    seg1 = ClipSegment(start_seconds=2.0, end_seconds=8.0, order_index=0)
    seg2 = ClipSegment(start_seconds=14.0, end_seconds=20.0, order_index=1)

    cmd = builder.build_reencode_filter_complex(
        input_path=input_file,
        segments=[seg1, seg2],
        output_path=output_file,
        has_audio=True,
    )

    assert "-filter_complex" in cmd
    filter_idx = cmd.index("-filter_complex")
    filter_str = cmd[filter_idx + 1]

    # Verify video trims
    assert "[0:v]trim=start=2.000:end=8.000,setpts=PTS-STARTPTS[v0]" in filter_str
    assert "[0:v]trim=start=14.000:end=20.000,setpts=PTS-STARTPTS[v1]" in filter_str

    # Verify audio trims
    assert "[0:a]atrim=start=2.000:end=8.000,asetpts=PTS-STARTPTS[a0]" in filter_str
    assert "[0:a]atrim=start=14.000:end=20.000,asetpts=PTS-STARTPTS[a1]" in filter_str

    # Verify concat filter
    assert "[v0][a0][v1][a1]concat=n=2:v=1:a=1[outv][outa]" in filter_str
    assert "-map" in cmd
    assert "[outv]" in cmd
    assert "[outa]" in cmd
    assert "libx264" in cmd
    assert "aac" in cmd
    assert cmd[-1] == str(output_file)


def test_render_segments_pipeline_stream_copy_single_segment(tmp_path: Path) -> None:
    """Test render pipeline single-segment succeeds with stream-copy."""
    runner = MockFFmpegRunner(succeed=True)
    input_file = tmp_path / "input.mp4"
    input_file.write_bytes(b"INPUT_DATA")
    output_file = tmp_path / "rendered.mp4"

    seg = ClipSegment(start_seconds=1.0, end_seconds=5.0, order_index=0)

    strategy = render_segments_pipeline(
        input_path=input_file,
        segments=[seg],
        output_path=output_file,
        runner=runner,
    )

    assert strategy == "stream_copy"
    assert output_file.exists()
    assert output_file.stat().st_size > 0
    assert len(runner.executed_commands) == 1
    assert "copy" in runner.executed_commands[0]


def test_render_segments_pipeline_stream_copy_multi_segment(tmp_path: Path) -> None:
    """Test render pipeline multi-segment succeeds with chunk-based stream-copy concat."""
    runner = MockFFmpegRunner(succeed=True)
    input_file = tmp_path / "input.mp4"
    input_file.write_bytes(b"INPUT_DATA")
    output_file = tmp_path / "rendered.mp4"

    seg1 = ClipSegment(start_seconds=1.0, end_seconds=5.0, order_index=0)
    seg2 = ClipSegment(start_seconds=10.0, end_seconds=15.0, order_index=1)

    strategy = render_segments_pipeline(
        input_path=input_file,
        segments=[seg1, seg2],
        output_path=output_file,
        runner=runner,
    )

    assert strategy == "stream_copy"
    assert output_file.exists()
    assert output_file.stat().st_size > 0
    # 2 chunk commands + 1 concat command = 3 commands total
    assert len(runner.executed_commands) == 3


def test_render_segments_pipeline_fallback_to_reencode(tmp_path: Path) -> None:
    """Test fallback to H.264/AAC re-encode when stream-copy concat fails."""
    runner = MockFFmpegRunner(succeed=True, fail_stream_copy=True)
    input_file = tmp_path / "input.mp4"
    input_file.write_bytes(b"INPUT_DATA")
    output_file = tmp_path / "rendered.mp4"

    seg = ClipSegment(start_seconds=1.0, end_seconds=5.0, order_index=0)

    strategy = render_segments_pipeline(
        input_path=input_file,
        segments=[seg],
        output_path=output_file,
        runner=runner,
    )

    assert strategy == "reencode"
    assert output_file.exists()
    assert output_file.stat().st_size > 0
    # First command was stream_copy (failed), second was reencode (succeeded)
    assert len(runner.executed_commands) == 2
    assert "copy" in runner.executed_commands[0]
    assert "libx264" in runner.executed_commands[1]


def test_render_segments_pipeline_force_reencode(tmp_path: Path) -> None:
    """Test force_reencode skips stream-copy and executes re-encode directly."""
    runner = MockFFmpegRunner(succeed=True)
    input_file = tmp_path / "input.mp4"
    input_file.write_bytes(b"INPUT_DATA")
    output_file = tmp_path / "rendered.mp4"

    seg = ClipSegment(start_seconds=1.0, end_seconds=5.0, order_index=0)

    strategy = render_segments_pipeline(
        input_path=input_file,
        segments=[seg],
        output_path=output_file,
        runner=runner,
        force_reencode=True,
    )

    assert strategy == "reencode"
    assert len(runner.executed_commands) == 1
    assert "libx264" in runner.executed_commands[0]


def test_render_segments_pipeline_all_fail_raises(tmp_path: Path) -> None:
    """Test render pipeline raises RuntimeError when both stream-copy and re-encode fail."""
    runner = MockFFmpegRunner(succeed=False, error_message="Fatal codec failure")
    input_file = tmp_path / "input.mp4"
    input_file.write_bytes(b"INPUT_DATA")
    output_file = tmp_path / "rendered.mp4"

    seg = ClipSegment(start_seconds=1.0, end_seconds=5.0, order_index=0)

    with pytest.raises(RuntimeError, match="Fatal codec failure"):
        render_segments_pipeline(
            input_path=input_file,
            segments=[seg],
            output_path=output_file,
            runner=runner,
        )
