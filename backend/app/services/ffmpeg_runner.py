"""FFmpeg command builder and runner abstraction module.

Provides injectable runner protocol and command construction for rendering video segments:
- Prefers safe stream-copy concat when compatible.
- Falls back to H.264/AAC re-encode when stream-copy is incompatible or fails.
- Supports single-segment cutting and multi-segment concat pipelines.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable

from app.core.config import settings
from app.models.clip import ClipSegment

logger = logging.getLogger(__name__)


@runtime_checkable
class FFmpegRunner(Protocol):
    """Injectable abstraction for executing FFmpeg / CLI commands."""

    def run(
        self,
        cmd: Sequence[str],
        timeout: float | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Execute command and return completed process."""
        ...


class SubprocessFFmpegRunner:
    """Default production runner invoking system FFmpeg subprocesses."""

    def run(
        self,
        cmd: Sequence[str],
        timeout: float | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run command list via subprocess.run."""
        logger.debug("Running FFmpeg CLI command: %s", " ".join(cmd))
        return subprocess.run(
            list(cmd),
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout or 3600.0,
        )


class MockFFmpegRunner:
    """Mock FFmpeg runner for unit testing command construction and failure rollback.

    Features:
    - Captures all executed command lists in `executed_commands`.
    - Allows simulating failures for specific flags or step counts.
    - Writes dummy output bytes to target file when execution succeeds so downstream
      filesystem validations pass.
    """

    def __init__(
        self,
        succeed: bool = True,
        fail_stream_copy: bool = False,
        fail_at_call_count: int | None = None,
        fail_on_substr: str | None = None,
        error_message: str = "Simulated FFmpeg execution failure",
        dummy_content: bytes = b"MOCK_RENDERED_VIDEO_DATA_OK",
    ) -> None:
        self.succeed = succeed
        self.fail_stream_copy = fail_stream_copy
        self.fail_at_call_count = fail_at_call_count
        self.fail_on_substr = fail_on_substr
        self.error_message = error_message
        self.dummy_content = dummy_content
        self.executed_commands: list[list[str]] = []

    def run(
        self,
        cmd: Sequence[str],
        timeout: float | None = None,
    ) -> subprocess.CompletedProcess[str]:
        cmd_list = list(cmd)
        self.executed_commands.append(cmd_list)
        call_index = len(self.executed_commands)

        # Check failure conditions
        is_stream_copy = "-c" in cmd_list and "copy" in cmd_list
        should_fail = (
            not self.succeed
            or (self.fail_stream_copy and is_stream_copy)
            or (self.fail_at_call_count is not None and call_index == self.fail_at_call_count)
            or (
                self.fail_on_substr is not None
                and any(self.fail_on_substr in arg for arg in cmd_list)
            )
        )

        if should_fail:
            return subprocess.CompletedProcess(
                args=cmd_list,
                returncode=1,
                stdout="",
                stderr=self.error_message,
            )

        # On success, write dummy content to output file if specified at last arg
        output_target = cmd_list[-1]
        try:
            target_path = Path(output_target)
            if target_path.parent.exists():
                target_path.write_bytes(self.dummy_content)
        except Exception:
            pass

        return subprocess.CompletedProcess(
            args=cmd_list,
            returncode=0,
            stdout="OK",
            stderr="",
        )


class FFmpegCommandBuilder:
    """Builds standard FFmpeg commands for clipping, stream-copy concat, and re-encoding."""

    def __init__(self, ffmpeg_path: str | None = None) -> None:
        self.ffmpeg_path = ffmpeg_path or settings.ffmpeg_path

    def build_stream_copy_single_segment(
        self,
        input_path: Path,
        start_seconds: float,
        end_seconds: float,
        output_path: Path,
    ) -> list[str]:
        """Build single segment fast stream-copy command."""
        return [
            self.ffmpeg_path,
            "-y",
            "-ss",
            f"{start_seconds:.3f}",
            "-to",
            f"{end_seconds:.3f}",
            "-i",
            str(input_path),
            "-c",
            "copy",
            str(output_path),
        ]

    def build_stream_copy_chunk(
        self,
        input_path: Path,
        start_seconds: float,
        end_seconds: float,
        chunk_path: Path,
    ) -> list[str]:
        """Build segment chunk stream-copy command with zeroed timestamps."""
        return [
            self.ffmpeg_path,
            "-y",
            "-ss",
            f"{start_seconds:.3f}",
            "-to",
            f"{end_seconds:.3f}",
            "-i",
            str(input_path),
            "-c",
            "copy",
            "-avoid_negative_ts",
            "make_zero",
            str(chunk_path),
        ]

    def build_concat_demuxer(
        self,
        manifest_path: Path,
        output_path: Path,
        copy_streams: bool = True,
    ) -> list[str]:
        """Build concat demuxer command from manifest file."""
        cmd = [
            self.ffmpeg_path,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(manifest_path),
        ]
        if copy_streams:
            cmd.extend(["-c", "copy"])
        else:
            cmd.extend(["-c:v", "libx264", "-c:a", "aac"])
        cmd.append(str(output_path))
        return cmd

    def build_reencode_single_segment(
        self,
        input_path: Path,
        start_seconds: float,
        end_seconds: float,
        output_path: Path,
        has_audio: bool = True,
    ) -> list[str]:
        """Build single segment re-encode command (H.264/AAC fallback)."""
        cmd = [
            self.ffmpeg_path,
            "-y",
            "-ss",
            f"{start_seconds:.3f}",
            "-to",
            f"{end_seconds:.3f}",
            "-i",
            str(input_path),
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "22",
        ]
        if has_audio:
            cmd.extend(["-c:a", "aac"])
        else:
            cmd.append("-an")
        cmd.append(str(output_path))
        return cmd

    def build_reencode_filter_complex(
        self,
        input_path: Path,
        segments: Sequence[ClipSegment],
        output_path: Path,
        has_audio: bool = True,
    ) -> list[str]:
        """Build multi-segment filter_complex re-encode command (H.264/AAC fallback)."""
        filter_parts: list[str] = []
        n = len(segments)
        for i, seg in enumerate(segments):
            filter_parts.append(
                f"[0:v]trim=start={seg.start_seconds:.3f}:end={seg.end_seconds:.3f},"
                f"setpts=PTS-STARTPTS[v{i}];"
            )
            if has_audio:
                filter_parts.append(
                    f"[0:a]atrim=start={seg.start_seconds:.3f}:end={seg.end_seconds:.3f},"
                    f"asetpts=PTS-STARTPTS[a{i}];"
                )

        concat_inputs: list[str] = []
        for i in range(n):
            concat_inputs.append(f"[v{i}]")
            if has_audio:
                concat_inputs.append(f"[a{i}]")

        audio_flag = 1 if has_audio else 0
        concat_filter = f"{''.join(concat_inputs)}concat=n={n}:v=1:a={audio_flag}"
        if has_audio:
            concat_filter += "[outv][outa]"
        else:
            concat_filter += "[outv]"
        filter_parts.append(concat_filter)

        filter_complex_str = "".join(filter_parts)

        cmd = [
            self.ffmpeg_path,
            "-y",
            "-i",
            str(input_path),
            "-filter_complex",
            filter_complex_str,
            "-map",
            "[outv]",
        ]
        if has_audio:
            cmd.extend([
                "-map",
                "[outa]",
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "22",
                "-c:a",
                "aac",
            ])
        else:
            cmd.extend([
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "22",
                "-an",
            ])
        cmd.append(str(output_path))
        return cmd


def render_segments_pipeline(
    input_path: Path,
    segments: Sequence[ClipSegment],
    output_path: Path,
    runner: FFmpegRunner,
    builder: FFmpegCommandBuilder | None = None,
    force_reencode: bool = False,
    has_audio: bool = True,
) -> str:
    """Render ordered clip segments to output_path using injectable runner.

    Strategy:
    - Sorts segments sequentially by order_index, start_seconds, and id.
    - Prefers safe stream-copy concat when compatible and not force_reencode.
    - Falls back to H.264/AAC re-encode on stream-copy failure or when requested.

    Returns:
        str: Applied rendering strategy ("stream_copy" or "reencode").
    """
    cmd_builder = builder or FFmpegCommandBuilder()
    sorted_segments = sorted(
        segments,
        key=lambda c: (c.order_index, c.start_seconds, getattr(c, "id", 0) or 0),
    )

    if not sorted_segments:
        raise ValueError("Cannot render video without clip segments")

    # Clean up output path before starting
    if output_path.exists():
        try:
            output_path.unlink()
        except Exception:
            pass

    # Attempt 1: Safe stream-copy concat if not explicitly forcing re-encode
    if not force_reencode:
        try:
            if len(sorted_segments) == 1:
                seg = sorted_segments[0]
                copy_cmd = cmd_builder.build_stream_copy_single_segment(
                    input_path=input_path,
                    start_seconds=seg.start_seconds,
                    end_seconds=seg.end_seconds,
                    output_path=output_path,
                )
                res = runner.run(copy_cmd)
                if res.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
                    logger.info("Successfully rendered single segment using stream_copy")
                    return "stream_copy"
            else:
                # Multi-segment stream-copy chunk + concat demuxer workflow
                chunk_dir = output_path.parent / f".tmp_chunks_{output_path.stem}"
                chunk_dir.mkdir(parents=True, exist_ok=True)
                chunk_paths: list[Path] = []
                all_chunks_ok = True

                try:
                    for i, seg in enumerate(sorted_segments):
                        chunk_file = chunk_dir / f"chunk_{i:04d}{output_path.suffix}"
                        chunk_cmd = cmd_builder.build_stream_copy_chunk(
                            input_path=input_path,
                            start_seconds=seg.start_seconds,
                            end_seconds=seg.end_seconds,
                            chunk_path=chunk_file,
                        )
                        chunk_res = runner.run(chunk_cmd)
                        if (
                            chunk_res.returncode != 0
                            or not chunk_file.exists()
                            or chunk_file.stat().st_size == 0
                        ):
                            all_chunks_ok = False
                            break
                        chunk_paths.append(chunk_file)

                    if all_chunks_ok and len(chunk_paths) == len(sorted_segments):
                        manifest_file = chunk_dir / "concat_manifest.txt"
                        manifest_lines = [
                            f"file '{p.resolve().as_posix()}'" for p in chunk_paths
                        ]
                        manifest_file.write_text("\n".join(manifest_lines), encoding="utf-8")

                        concat_cmd = cmd_builder.build_concat_demuxer(
                            manifest_path=manifest_file,
                            output_path=output_path,
                            copy_streams=True,
                        )
                        concat_res = runner.run(concat_cmd)
                        if (
                            concat_res.returncode == 0
                            and output_path.exists()
                            and output_path.stat().st_size > 0
                        ):
                            logger.info(
                                "Successfully rendered multi-segment concat using stream_copy"
                            )
                            return "stream_copy"
                finally:
                    if chunk_dir.exists():
                        shutil.rmtree(chunk_dir, ignore_errors=True)

        except Exception as copy_err:
            logger.warning(
                "Stream-copy concat attempt failed (%s), falling back to H.264/AAC re-encode",
                copy_err,
            )

    # Attempt 2: Re-encode fallback (H.264 / AAC)
    if output_path.exists():
        try:
            output_path.unlink()
        except Exception:
            pass

    logger.info("Rendering clip segments via H.264/AAC re-encode fallback")
    if len(sorted_segments) == 1:
        seg = sorted_segments[0]
        reencode_cmd = cmd_builder.build_reencode_single_segment(
            input_path=input_path,
            start_seconds=seg.start_seconds,
            end_seconds=seg.end_seconds,
            output_path=output_path,
            has_audio=has_audio,
        )
    else:
        reencode_cmd = cmd_builder.build_reencode_filter_complex(
            input_path=input_path,
            segments=sorted_segments,
            output_path=output_path,
            has_audio=has_audio,
        )

    res = runner.run(reencode_cmd)
    if res.returncode != 0:
        err_detail = res.stderr.strip() if res.stderr else f"exit code {res.returncode}"
        raise RuntimeError(f"FFmpeg re-encode failed: {err_detail}")

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("FFmpeg re-encode completed but output file is missing or empty")

    return "reencode"
