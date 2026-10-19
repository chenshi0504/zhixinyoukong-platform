"""
YOLO11 + BoTSORT 车辆检测跟踪
使用 ultralytics YOLO11 内置跟踪器进行目标检测与多目标跟踪
检测目标: car, bus, truck
每15分钟输出分时段流量统计

用法:
    python yolo11_tracker.py                          # 默认 test1.mp4
    python yolo11_tracker.py --video test2.mp4        # 指定视频
    python yolo11_tracker.py --video path/to/video.mp4 --model yolo11n.pt
"""
import os
import sys
import time
import json
import argparse
import cv2
import numpy as np
import matplotlib.pyplot as plt

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

from ultralytics import YOLO

# COCO 类别中车辆相关的 class_id
# 2=car, 5=bus, 7=truck
VEHICLE_CLASSES = {2: 'car', 5: 'bus', 7: 'truck'}


def parse_args():
    parser = argparse.ArgumentParser(description='YOLO11 + BoTSORT 车辆检测跟踪')
    parser.add_argument('--video', type=str, default='test1.mp4',
                        help='视频文件名或完整路径')
    parser.add_argument('--model', type=str, default='yolo11n.pt',
                        help='YOLO11 模型 (yolo11 n/s/m/l/x.pt)')
    parser.add_argument('--conf', type=float, default=0.50, help='置信度阈值')
    parser.add_argument('--iou', type=float, default=0.45, help='NMS IOU阈值')
    parser.add_argument('--output', type=str, default=None, help='输出视频路径')
    parser.add_argument('--no-show', action='store_true', help='不显示检测窗口')
    return parser.parse_args()


def resolve_video_path(video_arg):
    """解析视频路径：支持文件名或完整路径"""
    if os.path.isabs(video_arg) and os.path.exists(video_arg):
        return video_arg
    for d in [os.path.join(BASE_DIR, 'uploads'),
              os.path.join(BASE_DIR, 'data', 'video'),
              os.path.join(BASE_DIR, '..'),
              BASE_DIR]:
        p = os.path.join(d, video_arg)
        if os.path.exists(p):
            return p
    return None


def main():
    args = parse_args()

    video_path = resolve_video_path(args.video)
    if not video_path:
        print(f'[错误] 视频文件不存在: {args.video}')
        sys.exit(1)

    video_basename = os.path.splitext(os.path.basename(video_path))[0]
    output_path = args.output or os.path.join(BASE_DIR, 'outputs',
                                               f'{video_basename}_yolo11_output.mp4')
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    stats_file = os.path.join(BASE_DIR, f'{video_basename}_yolo11.txt')

    print('=' * 70)
    print('YOLO11 + BoTSORT 车辆检测跟踪')
    print('=' * 70)
    print(f'视频文件: {video_path}')
    print(f'模型: {args.model}')
    print(f'置信度: {args.conf}  IOU: {args.iou}')
    print(f'输出视频: {output_path}')
    print(f'统计文件: {stats_file}')
    print('=' * 70)

    # ---- 加载 YOLO11 模型 ----
    print('[1/2] 加载 YOLO11 模型...')
    model = YOLO(args.model)
    print(f'  模型加载完成: {args.model}')

    # ---- 打开视频 ----
    print('[2/2] 打开视频...')
    vid = cv2.VideoCapture(video_path)
    if not vid.isOpened():
        print(f'[错误] 无法打开视频: {video_path}')
        sys.exit(1)

    width = int(vid.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(vid.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = vid.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(vid.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f'  分辨率: {width}x{height}  帧率: {fps:.1f}  总帧数: {total_frames}')

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    # 统计变量
    vehicle_ids = set()
    car_count = bus_count = truck_count = 0
    period_stats = []
    prev_car = prev_bus = prev_truck = prev_total = 0

    f_stats = open(stats_file, 'w', encoding='utf-8')
    frame_num = 0
    print('\n开始检测...\n')

    # 预生成颜色映射
    cmap = plt.get_cmap('tab20b')
    colors_map = [cmap(i)[:3] for i in np.linspace(0, 1, 20)]

    while True:
        ret, frame = vid.read()
        if not ret:
            break

        frame_num += 1
        start_time = time.time()

        # ---- YOLO11 检测 + 内置 BoTSORT 跟踪 ----
        # model.track() 自动进行检测+跟踪，返回带 track_id 的结果
        # classes=[2,5,7] 只检测 car, bus, truck
        results = model.track(frame, conf=args.conf, iou=args.iou,
                              classes=[2, 5, 7], persist=True, verbose=False,
                              tracker='botsort.yaml')

        detected_count = 0
        for r in results:
            if r.boxes is None or r.boxes.id is None:
                continue
            boxes = r.boxes
            for i in range(len(boxes)):
                cls_id = int(boxes.cls[i])
                if cls_id not in VEHICLE_CLASSES:
                    continue

                track_id = int(boxes.id[i])
                x1, y1, x2, y2 = boxes.xyxy[i].cpu().numpy()
                class_name = VEHICLE_CLASSES[cls_id]
                detected_count += 1

                # 绘制
                color = colors_map[track_id % len(colors_map)]
                color = [int(c * 255) for c in color]
                cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
                label = f'{class_name}-{track_id}'
                cv2.rectangle(frame, (int(x1), int(y1) - 25),
                              (int(x1) + len(label) * 12, int(y1)), color, -1)
                cv2.putText(frame, label, (int(x1), int(y1) - 7),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)

                # 统计新车辆
                if track_id not in vehicle_ids:
                    vehicle_ids.add(track_id)
                    if class_name == 'car':
                        car_count += 1
                    elif class_name == 'bus':
                        bus_count += 1
                    elif class_name == 'truck':
                        truck_count += 1

        total_count = car_count + bus_count + truck_count
        cv2.putText(frame, f'Tracked: {detected_count}  Total: {total_count}',
                    (10, 35), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

        det_fps = 1.0 / (time.time() - start_time) if (time.time() - start_time) > 0 else 0
        if frame_num % 30 == 0:
            print(f'帧 {frame_num}/{total_frames}  '
                  f'FPS: {det_fps:.1f}  '
                  f'car:{car_count} bus:{bus_count} truck:{truck_count} total:{total_count}')

        # ---- 每15分钟统计 ----
        video_time_min = (frame_num / fps) / 60.0
        period_idx = int(video_time_min / 15)

        is_period_end = (frame_num == total_frames) or \
                        (len(period_stats) < period_idx + 1 and video_time_min >= (len(period_stats) + 1) * 15)

        if is_period_end and len(period_stats) <= period_idx:
            p_car = car_count - prev_car
            p_bus = bus_count - prev_bus
            p_truck = truck_count - prev_truck
            p_total = total_count - prev_total
            period_num = len(period_stats) + 1
            line = f'第{period_num}组  {video_time_min:.1f}  {p_car}  {p_bus}  {p_truck}  {p_total}'
            f_stats.write(line + '\n')
            f_stats.flush()
            period_stats.append(line)
            print(f'[统计] {line}')
            prev_car, prev_bus, prev_truck, prev_total = car_count, bus_count, truck_count, total_count

        # ---- 保存共享数据供Web前端读取 ----
        if frame_num % 3 == 0:
            try:
                shared_frame_path = os.path.join(BASE_DIR, 'shared_frame.jpg')
                cv2.imwrite(shared_frame_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            except Exception:
                pass

        shared_data = {
            'status': 'running',
            'frameNum': frame_num,
            'totalFrames': total_frames,
            'fps': round(det_fps, 1),
            'objectCount': detected_count,
            'carCount': car_count,
            'busCount': bus_count,
            'truckCount': truck_count,
            'totalCount': total_count,
            'progress': int((frame_num / total_frames) * 100) if total_frames > 0 else 0
        }
        try:
            with open(os.path.join(BASE_DIR, 'shared_detection_data.json'), 'w', encoding='utf-8') as sf:
                json.dump(shared_data, sf, ensure_ascii=False)
        except Exception:
            pass

        out.write(frame)

        if not args.no_show:
            cv2.imshow('YOLO11 + BoTSORT', frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    # ---- 写入最终统计 ----
    if frame_num == total_frames and total_count > prev_total:
        p_car = car_count - prev_car
        p_bus = bus_count - prev_bus
        p_truck = truck_count - prev_truck
        p_total = total_count - prev_total
        period_num = len(period_stats) + 1
        video_time_min = (frame_num / fps) / 60.0
        line = f'第{period_num}组  {video_time_min:.1f}  {p_car}  {p_bus}  {p_truck}  {p_total}'
        f_stats.write(line + '\n')

    total_time_min = (total_frames / fps) / 60.0 if fps > 0 else 0
    final_line = f'总计  {total_time_min:.2f}  {car_count}  {bus_count}  {truck_count}  {total_count}'
    f_stats.write(final_line + '\n')
    f_stats.close()

    # 保存最终JSON状态
    final_data = {
        'status': 'completed',
        'frameNum': total_frames,
        'totalFrames': total_frames,
        'fps': 0,
        'objectCount': 0,
        'carCount': car_count,
        'busCount': bus_count,
        'truckCount': truck_count,
        'totalCount': total_count,
        'progress': 100
    }
    try:
        with open(os.path.join(BASE_DIR, 'shared_detection_data.json'), 'w', encoding='utf-8') as sf:
            json.dump(final_data, sf, ensure_ascii=False)
    except Exception:
        pass

    vid.release()
    out.release()
    cv2.destroyAllWindows()

    print('\n' + '=' * 70)
    print('检测完成!')
    print(f'  小汽车: {car_count}  公交车: {bus_count}  卡车: {truck_count}  总计: {total_count}')
    print(f'  输出视频: {output_path}')
    print(f'  统计文件: {stats_file}')
    print('=' * 70)


if __name__ == '__main__':
    main()
