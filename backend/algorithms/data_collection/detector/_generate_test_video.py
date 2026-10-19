"""
生成一段合成测试视频 test1.mp4，用于数据采集模块的默认演示。
不依赖 OpenCV，使用纯 Python 生成一段最小可用的 MP4 占位视频。
如果 OpenCV 可用，则生成带有移动方块的 10 秒视频。

用法:
    python _generate_test_video.py               # 输出到 data/video/test1.mp4
    python _generate_test_video.py --output path  # 指定输出路径
"""
import os
import sys
import struct
import argparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUTPUT = os.path.join(BASE_DIR, 'data', 'video', 'test1.mp4')


def generate_with_opencv(output_path, duration=10, fps=25, width=640, height=480):
    """使用 OpenCV 生成带有移动方块的测试视频。"""
    import cv2
    import numpy as np

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    total_frames = duration * fps
    for i in range(total_frames):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:] = (40, 40, 40)  # 深灰背景

        # 模拟 2 辆 "车"（彩色矩形）从左向右移动
        t = i / total_frames
        x1 = int(t * (width + 100)) - 100
        x2 = int(t * (width + 100)) - 300

        # 车 1（蓝色）
        cv2.rectangle(frame, (x1, 200), (x1 + 80, 240), (255, 100, 50), -1)
        # 车 2（红色）
        cv2.rectangle(frame, (x2, 300), (x2 + 80, 340), (50, 50, 255), -1)

        # 道路标线
        cv2.line(frame, (0, 260), (width, 260), (200, 200, 200), 1)
        cv2.line(frame, (0, 180), (width, 180), (200, 200, 200), 1)
        cv2.line(frame, (0, 360), (width, 360), (200, 200, 200), 1)

        # 帧号水印
        cv2.putText(frame, f'TEST FRAME {i+1}/{total_frames}', (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 1)

        writer.write(frame)

    writer.release()
    print(f'[OK] OpenCV 测试视频已生成: {output_path}')
    print(f'     时长: {duration}s, {fps}fps, {width}x{height}')


def generate_minimal_mp4(output_path):
    """生成最小可播放的 MP4 占位文件（无需 OpenCV）。
    仅包含一个空 moov + mdat，可被 FFmpeg/OpenCV 识别为有效文件。"""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # 最小 MP4: ftyp + moov + mdat
    ftyp = b'\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2mp41'
    # 空 moov（只含 mvhd）
    mvhd = b'\x00\x00\x00\x6Cmvhd' + b'\x00' * 100
    moov = struct.pack('>I', len(mvhd) + 8) + b'moov' + mvhd
    mdat = b'\x00\x00\x00\x08mdat'

    with open(output_path, 'wb') as f:
        f.write(ftyp)
        f.write(moov)
        f.write(mdat)

    print(f'[OK] 最小占位 MP4 已生成: {output_path}')
    print(f'     注意: 此文件仅为占位，无实际视频帧。')
    print(f'     建议使用真实测试视频替换。')


def main():
    parser = argparse.ArgumentParser(description='生成测试视频 test1.mp4')
    parser.add_argument('--output', '-o', default=DEFAULT_OUTPUT, help='输出路径')
    parser.add_argument('--duration', '-d', type=int, default=10, help='视频时长(秒)')
    args = parser.parse_args()

    try:
        generate_with_opencv(args.output, duration=args.duration)
    except ImportError:
        print('[提示] OpenCV 未安装，将生成最小占位 MP4')
        generate_minimal_mp4(args.output)


if __name__ == '__main__':
    main()
