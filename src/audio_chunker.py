import os
import re
import subprocess
import tempfile
import imageio_ffmpeg

def get_ffmpeg_cmd():
    return imageio_ffmpeg.get_ffmpeg_exe()

def get_subprocess_flags():
    startupinfo = None
    creation_flags = 0
    if os.name == 'nt':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        creation_flags = subprocess.CREATE_NO_WINDOW | getattr(subprocess, 'BELOW_NORMAL_PRIORITY_CLASS', 0x00004000)
    return startupinfo, creation_flags

def parse_track_lang(filename):
    """Extract language code or identifier from filename."""
    match = re.search(r"_audio_(.+)\.(mp3|m4a|webm|wav|aac)$", filename, re.IGNORECASE)
    if match:
        return match.group(1)
    base = os.path.splitext(filename)[0]
    return base

def split_audio_into_chunks(audio_path, initial_sec=6.0, output_dir=None):
    """
    Splits an audio file into 2 chunks:
      - chunk_0: [0, initial_sec] (for initial instant buffer playback)
      - chunk_1: [initial_sec, end] (for background streaming decode)
    Returns:
      (chunk_0_path, chunk_1_path)
    """
    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="de_chunk_")
    os.makedirs(output_dir, exist_ok=True)

    base_name = os.path.splitext(os.path.basename(audio_path))[0]
    ext = os.path.splitext(audio_path)[1].lower()
    if not ext:
        ext = ".mp3"

    chunk0_path = os.path.join(output_dir, f"{base_name}_chunk0{ext}")
    chunk1_path = os.path.join(output_dir, f"{base_name}_chunk1{ext}")

    ffmpeg = get_ffmpeg_cmd()
    startupinfo, creation_flags = get_subprocess_flags()

    # Determine encoder by extension to guarantee clean boundary cutting
    codec_args = ['-c:a', 'copy']
    if ext == '.mp3':
        codec_args = ['-c:a', 'libmp3lame', '-b:a', '192k']
    elif ext in ('.m4a', '.aac'):
        codec_args = ['-c:a', 'aac', '-b:a', '192k']

    # 1. Cut Chunk 0: 0 ~ initial_sec
    cmd0 = [
        ffmpeg, '-y',
        '-i', audio_path,
        '-t', str(initial_sec)
    ] + codec_args + [chunk0_path]

    subprocess.run(
        cmd0,
        capture_output=True,
        startupinfo=startupinfo,
        creationflags=creation_flags,
        check=True
    )

    # 2. Cut Chunk 1: initial_sec ~ end (sample-accurate seeking with -ss after -i)
    cmd1 = [
        ffmpeg, '-y',
        '-i', audio_path,
        '-ss', str(initial_sec)
    ] + codec_args + [chunk1_path]

    subprocess.run(
        cmd1,
        capture_output=True,
        startupinfo=startupinfo,
        creationflags=creation_flags,
        check=True
    )

    return chunk0_path, chunk1_path

def concatenate_chunks(chunk_paths, output_path):
    """
    Seamlessly concatenates multiple audio chunks into a single unified file.
    Uses ffmpeg concat demuxer.
    """
    if not chunk_paths:
        raise ValueError("No chunk paths provided for concatenation.")
    if len(chunk_paths) == 1:
        import shutil
        shutil.copyfile(chunk_paths[0], output_path)
        return output_path

    ffmpeg = get_ffmpeg_cmd()
    startupinfo, creation_flags = get_subprocess_flags()

    tmp_list = os.path.join(tempfile.gettempdir(), f"concat_list_{os.getpid()}_{np_hash()}.txt")
    with open(tmp_list, 'w', encoding='utf-8') as f:
        for p in chunk_paths:
            escaped = os.path.abspath(p).replace('\\', '/')
            f.write(f"file '{escaped}'\n")

    try:
        cmd = [
            ffmpeg, '-y',
            '-f', 'concat',
            '-safe', '0',
            '-i', tmp_list,
            '-c', 'copy',
            output_path
        ]
        res = subprocess.run(
            cmd,
            capture_output=True,
            startupinfo=startupinfo,
            creationflags=creation_flags
        )
        if res.returncode != 0:
            # Fallback to re-encoding if stream copy fails
            ext = os.path.splitext(output_path)[1].lower()
            re_codec = ['-c:a', 'libmp3lame'] if ext == '.mp3' else ['-c:a', 'aac']
            cmd_fallback = [
                ffmpeg, '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', tmp_list
            ] + re_codec + [output_path]
            subprocess.run(
                cmd_fallback,
                capture_output=True,
                startupinfo=startupinfo,
                creationflags=creation_flags,
                check=True
            )
    finally:
        if os.path.exists(tmp_list):
            try:
                os.remove(tmp_list)
            except Exception:
                pass

    return output_path

def np_hash():
    import random
    return f"{random.randint(100000, 999999)}"
