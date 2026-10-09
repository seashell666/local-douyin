# -*- coding: utf-8 -*-
"""
纯 Python MP4 元数据解析器（无需 ffprobe）
解析 ISO BMFF (MP4) 的 moov/tkhd/mdhd box 获取 duration/width/height
"""
import struct


def _read_box_header(f):
    """读取一个 box 的 header，返回 (size, box_type)"""
    data = f.read(8)
    if len(data) < 8:
        return 0, b""
    size = struct.unpack(">I", data[:4])[0]
    box_type = data[4:8]
    if size == 1:  # 64-bit size
        size = struct.unpack(">Q", f.read(8))[0]
    return size, box_type


def _find_box(f, target_type, end_pos):
    """在当前位置到 end_pos 之间查找指定类型的 box，返回其数据起始位置"""
    while f.tell() < end_pos:
        start = f.tell()
        size, box_type = _read_box_header(f)
        if size == 0:
            break
        if box_type == target_type:
            return start
        f.seek(start + size)
    return None


def parse_mp4_metadata(filepath):
    """
    解析 MP4 文件，返回 {duration, width, height, timescale}
    duration 单位为秒
    """
    try:
        with open(filepath, "rb") as f:
            f.seek(0, 2)
            file_size = f.tell()
            f.seek(0)

            # 找 moov box
            moov_start = _find_box(f, b"moov", file_size)
            if not moov_start:
                return None

            # 读 moov header
            f.seek(moov_start)
            moov_size, _ = _read_box_header(f)
            moov_end = moov_start + moov_size

            # 找 mvhd（movie header，含 duration）
            mvhd_start = _find_box(f, b"mvhd", moov_end)
            duration = 0
            timescale = 0
            if mvhd_start:
                f.seek(mvhd_start + 8)  # 跳过 header
                version = f.read(1)[0]
                f.read(3)  # flags
                if version == 1:
                    f.read(8)  # creation_time
                    f.read(8)  # modification_time
                    timescale = struct.unpack(">I", f.read(4))[0]
                    duration = struct.unpack(">Q", f.read(8))[0]
                else:
                    f.read(4)
                    f.read(4)
                    timescale = struct.unpack(">I", f.read(4))[0]
                    duration = struct.unpack(">I", f.read(4))[0]

            # 找 trak -> tkhd（含 width/height）
            f.seek(moov_start + 8)
            width = 0
            height = 0
            while f.tell() < moov_end:
                trak_start = f.tell()
                size, box_type = _read_box_header(f)
                if size == 0:
                    break
                if box_type == b"trak":
                    trak_end = trak_start + size
                    tkhd_start = _find_box(f, b"tkhd", trak_end)
                    if tkhd_start:
                        f.seek(tkhd_start + 8)  # 跳过 size+type，指向 version
                        v = f.read(1)[0]
                        f.read(3)  # flags
                        if v == 1:
                            f.read(8)  # creation_time
                            f.read(8)  # modification_time
                            f.read(4)  # track_ID
                            f.read(4)  # reserved
                            f.read(8)  # duration
                        else:
                            f.read(4)  # creation_time
                            f.read(4)  # modification_time
                            f.read(4)  # track_ID
                            f.read(4)  # reserved
                            f.read(4)  # duration
                        f.read(8)   # reserved (2 uint32)
                        f.read(2)   # layer
                        f.read(2)   # alternate_group
                        f.read(2)   # volume
                        f.read(2)   # reserved
                        f.read(36)  # matrix (9 uint32)
                        # width 和 height 是 16.16 fixed point
                        w_raw = struct.unpack(">I", f.read(4))[0]
                        h_raw = struct.unpack(">I", f.read(4))[0]
                        width = w_raw / 65536.0
                        height = h_raw / 65536.0
                        if width > 0 and height > 0:
                            break
                    f.seek(trak_end)
                else:
                    f.seek(trak_start + size)

            duration_sec = round(duration / timescale, 2) if timescale > 0 else 0
            return {
                "duration": duration_sec,
                "width": int(width),
                "height": int(height),
                "timescale": timescale,
            }
    except Exception:
        return None


# MP3 比特率表（MPEG1 Layer3）
MP3_BITRATES_V1_L3 = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0]
MP3_SAMPLE_RATES_V1 = [44100, 48000, 32000, 0]


def parse_mp3_metadata(filepath):
    """
    解析 MP3 文件（可能伪装为 .mp4），通过帧头估算时长。
    返回 {duration, width=0, height=0, format: 'mp3'}
    """
    try:
        import os
        file_size = os.path.getsize(filepath)
        with open(filepath, "rb") as f:
            # 跳过 ID3 标签
            header = f.read(3)
            if header == b"ID3":
                f.read(2)  # version
                flags = f.read(1)[0]
                # ID3v2 size (syncsafe integer)
                size_bytes = f.read(4)
                tag_size = ((size_bytes[0] & 0x7f) << 21) | ((size_bytes[1] & 0x7f) << 14) | \
                           ((size_bytes[2] & 0x7f) << 7) | (size_bytes[3] & 0x7f)
                if flags & 0x10:  # footer present
                    tag_size += 10
                f.seek(tag_size + 10)
            else:
                f.seek(0)

            # 找 MP3 帧同步（0xFF 0xFB 或 0xFF 0xF3 等）
            for _ in range(100):
                byte = f.read(1)
                if not byte:
                    break
                if byte[0] != 0xFF:
                    continue
                byte2 = f.read(1)
                if not byte2:
                    break
                # 检查帧同步：1111 1111 111x xxxx
                if (byte2[0] & 0xE0) != 0xE0:
                    f.seek(-1, 1)
                    continue
                # 读取帧头
                rest = f.read(2)
                if len(rest) < 2:
                    break
                b1 = byte2[0]
                b2 = rest[0]

                version = (b1 >> 3) & 0x03
                layer = (b1 >> 1) & 0x03
                bitrate_idx = (b2 >> 4) & 0x0F
                samplerate_idx = (b2 >> 2) & 0x03

                if version == 3 and layer == 1:  # MPEG1 Layer3
                    bitrate = MP3_BITRATES_V1_L3[bitrate_idx] * 1000
                    sample_rate = MP3_SAMPLE_RATES_V1[samplerate_idx]
                    if bitrate > 0 and sample_rate > 0:
                        # 估算时长（减去ID3标签大小）
                        audio_size = file_size - f.tell()
                        duration = audio_size * 8 / bitrate
                        return {
                            "duration": round(duration, 2),
                            "width": 0,
                            "height": 0,
                            "format": "mp3",
                            "bitrate": bitrate,
                        }
                break
    except Exception:
        pass
    return None


def parse_metadata(filepath):
    """
    统一入口：自动检测文件格式并解析元数据。
    支持 MP4 和 MP3。
    """
    try:
        with open(filepath, "rb") as f:
            magic = f.read(4)
        if magic[:3] == b"ID3" or magic[:2] == b"\xff\xfb":
            return parse_mp3_metadata(filepath)
        return parse_mp4_metadata(filepath)
    except Exception:
        return None


if __name__ == "__main__":
    import sys
    import os
    if len(sys.argv) > 1:
        result = parse_mp4_metadata(sys.argv[1])
        print(f"File: {sys.argv[1]}")
        print(f"Result: {result}")
    else:
        # 测试 data/videos 目录下第一个视频
        video_dir = os.path.join(os.path.dirname(__file__), "..", "data", "videos")
        videos = [f for f in os.listdir(video_dir) if f.endswith(".mp4")]
        if videos:
            path = os.path.join(video_dir, videos[0])
            result = parse_mp4_metadata(path)
            print(f"File: {videos[0]}")
            print(f"Result: {result}")
