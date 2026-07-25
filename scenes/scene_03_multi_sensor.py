# -*- coding: utf-8 -*-
"""场景03：多传感器集成 — RGB + Depth + Semantic Segmentation + 多危险叠加"""

import carla
import time
import os
import math
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, '..', 'output', 'scene_03_multi_sensor')
for sub in ['rgb', 'depth', 'semantic']:
    os.makedirs(os.path.join(OUTPUT_DIR, sub), exist_ok=True)

# ==================== 1. 连接 CARLA ====================
client = carla.Client('localhost', 2000)
client.set_timeout(20.0)
world = client.get_world()
print(f'[CONNECT] CARLA 地图: {world.get_map().name}')

# ==================== 2. 极端天气 ====================
weather = carla.WeatherParameters(
    cloudiness=100.0, precipitation=95.0,
    precipitation_deposits=85.0, wind_intensity=70.0,
    fog_density=85.0, fog_distance=8.0,
    sun_altitude_angle=-15.0, wetness=90.0,
)
world.set_weather(weather)
print('[WEATHER] 暴雨 + 浓雾 + 夜间')

# ==================== 3. 交通管理器（忽略红绿灯） ====================
traffic_manager = client.get_trafficmanager(8000)
traffic_manager.set_global_distance_to_leading_vehicle(2.5)
traffic_manager.set_synchronous_mode(False)
print('[TRAFFIC] 交通管理器已配置（忽略红绿灯）')

# ==================== 4. 生成主车 ====================
bp_lib = world.get_blueprint_library()
ego_bp = bp_lib.filter('vehicle.tesla.model3')[0]
spawn_points = world.get_map().get_spawn_points()
ego_sp = spawn_points[40]
ego_vehicle = world.try_spawn_actor(ego_bp, ego_sp)
if not ego_vehicle:
    for pt in spawn_points:
        ego_vehicle = world.try_spawn_actor(ego_bp, pt)
        if ego_vehicle:
            ego_sp = pt
            break
print(f'[EGO] {ego_vehicle.type_id}')

# ==================== 5. 传感器安装 ====================
SENSOR_POS = carla.Transform(carla.Location(x=1.5, z=2.4))

rgb_bp = bp_lib.find('sensor.camera.rgb')
rgb_bp.set_attribute('image_size_x', '1280')
rgb_bp.set_attribute('image_size_y', '720')
rgb_bp.set_attribute('fov', '90')
rgb_cam = world.spawn_actor(rgb_bp, SENSOR_POS, attach_to=ego_vehicle)

depth_bp = bp_lib.find('sensor.camera.depth')
depth_bp.set_attribute('image_size_x', '1280')
depth_bp.set_attribute('image_size_y', '720')
depth_bp.set_attribute('fov', '90')
depth_cam = world.spawn_actor(depth_bp, SENSOR_POS, attach_to=ego_vehicle)

sem_bp = bp_lib.find('sensor.camera.semantic_segmentation')
sem_bp.set_attribute('image_size_x', '1280')
sem_bp.set_attribute('image_size_y', '720')
sem_bp.set_attribute('fov', '90')
sem_cam = world.spawn_actor(sem_bp, SENSOR_POS, attach_to=ego_vehicle)

print('[SENSORS] RGB + Depth + SemanticSeg 已安装')

# ==================== 6. 传感器回调 ====================

def save_rgb(image):
    image.save_to_disk(os.path.join(OUTPUT_DIR, 'rgb', f'frame_{image.frame:06d}.png'))

def save_depth(image):
    data = np.frombuffer(image.raw_data, dtype=np.uint8)
    data = data.reshape((image.height, image.width, 4))
    depth_m = (data[:,:,2].astype(np.float32) +
               data[:,:,1].astype(np.float32) * 256 +
               data[:,:,0].astype(np.float32) * 65536) / 16777215.0 * 1000.0
    depth_gray = np.clip(depth_m / 100.0 * 255, 0, 255).astype(np.uint8)
    from PIL import Image
    img = Image.fromarray(depth_gray, mode='L')
    img.save(os.path.join(OUTPUT_DIR, 'depth', f'frame_{image.frame:06d}.png'))

def save_semantic(image):
    image.convert(carla.ColorConverter.CityScapesPalette)
    image.save_to_disk(os.path.join(OUTPUT_DIR, 'semantic', f'frame_{image.frame:06d}.png'))
    data = np.frombuffer(image.raw_data, dtype=np.uint8)
    data = data.reshape((image.height, image.width, 4))
    labels = data[:, :, 2]
    np.save(os.path.join(OUTPUT_DIR, 'semantic', f'labels_{image.frame:06d}.npy'), labels)

rgb_cam.listen(save_rgb)
depth_cam.listen(save_depth)
sem_cam.listen(save_semantic)
print('[CALLBACK] 三路传感器回调已注册')

# ==================== 7. 前车 ====================
lead_bp = bp_lib.filter('vehicle.audi.a2')[0]
yaw_rad = math.radians(ego_sp.rotation.yaw)
lead_x = ego_sp.location.x + 25 * math.cos(yaw_rad)
lead_y = ego_sp.location.y + 25 * math.sin(yaw_rad)
lead_sp = carla.Transform(
    carla.Location(x=lead_x, y=lead_y, z=ego_sp.location.z),
    ego_sp.rotation
)
lead_vehicle = world.try_spawn_actor(lead_bp, lead_sp)
if not lead_vehicle:
    for pt in spawn_points:
        if pt.location.distance(ego_sp.location) > 20:
            lead_vehicle = world.try_spawn_actor(lead_bp, pt)
            if lead_vehicle:
                break
print(f'[LEAD] 前车: {lead_vehicle.type_id}' if lead_vehicle else '[LEAD] 失败')

# ==================== 8. 行人（路边待命，不设目标=不动） ====================
road_right = 8.0
walker_bp = bp_lib.filter('walker.pedestrian.0007')[0]
wx = ego_sp.location.x + 30 * math.cos(yaw_rad) - road_right * math.sin(yaw_rad)
wy = ego_sp.location.y + 30 * math.sin(yaw_rad) + road_right * math.cos(yaw_rad)
walker_start = carla.Location(x=wx, y=wy, z=ego_sp.location.z)
walker = world.try_spawn_actor(walker_bp, carla.Transform(walker_start))

# 横穿终点（道路左侧）
dx = ego_sp.location.x + 30 * math.cos(yaw_rad) + road_right * math.sin(yaw_rad)
dy = ego_sp.location.y + 30 * math.sin(yaw_rad) - road_right * math.cos(yaw_rad)
walker_dest = carla.Location(x=dx, y=dy, z=ego_sp.location.z)

walker_ctrl = None
if walker:
    ctrl_bp = bp_lib.find('controller.ai.walker')
    walker_ctrl = world.spawn_actor(ctrl_bp, carla.Transform(), attach_to=walker)
    walker_ctrl.start()
    # 不设置 go_to_location，行人原地站立待命
    print(f'[WALKER] 行人已在路边待命 ({wx:.1f}, {wy:.1f})')
else:
    print('[WALKER] 失败')

# ==================== 9. 开启自动驾驶（忽略红绿灯） ====================
ego_vehicle.set_autopilot(True, 8000)
traffic_manager.ignore_lights_percentage(ego_vehicle, 100)
if lead_vehicle:
    lead_vehicle.set_autopilot(True, 8000)
    traffic_manager.ignore_lights_percentage(lead_vehicle, 100)
print('[AUTOPILOT] 两车自动驾驶已开启 (忽略红绿灯)')

# ==================== 10. 运行场景 ====================
print()
print('=' * 50)
print('  多传感器场景运行中 (20s)')
print('  RGB     -> output/rgb/')
print('  Depth   -> output/depth/')
print('  SemSeg  -> output/semantic/')
print('  红绿灯全部忽略 | 第 5s 前车急刹 | 第 3s 行人冲出')
print('=' * 50)
print()

brake_done = False
walker_triggered = False
try:
    for step in range(20):
        time.sleep(1)
        t = step + 1

        ego_v = ego_vehicle.get_velocity()
        speed = 3.6 * math.sqrt(ego_v.x**2 + ego_v.y**2 + ego_v.z**2)
        dist = lead_vehicle.get_location().distance(ego_vehicle.get_location()) if lead_vehicle else float('inf')

        msg = f'  [{t:2d}s] 速度:{speed:5.1f}km/h | 车距:{dist:5.1f}m'

        # 第 3 秒：行人突然冲出
        if t == 3 and walker_ctrl and not walker_triggered:
            walker_ctrl.go_to_location(walker_dest)
            walker_ctrl.set_max_speed(3.5)
            walker_triggered = True
            msg += ' >>> 行人冲出!'

        # 第 5 秒：前车急刹
        if t == 5 and lead_vehicle and not brake_done:
            lead_vehicle.apply_control(carla.VehicleControl(throttle=0.0, brake=1.0))
            brake_done = True
            msg += ' >>> 急刹!'

        print(msg)
        if lead_vehicle and dist < 1.5:
            print('  !!! 碰撞 !!!')
            break

except KeyboardInterrupt:
    print()
    print('[STOP] 用户中断')

# ==================== 11. 清理 ====================
print()
print('[CLEANUP]')
for s in [rgb_cam, depth_cam, sem_cam]:
    s.stop()

for a in [walker_ctrl, walker, lead_vehicle, ego_vehicle, rgb_cam, depth_cam, sem_cam]:
    try:
        a.destroy() if a else None
    except:
        pass

rgb_n = len(os.listdir(os.path.join(OUTPUT_DIR, 'rgb')))
depth_n = len(os.listdir(os.path.join(OUTPUT_DIR, 'depth')))
sem_n = len(os.listdir(os.path.join(OUTPUT_DIR, 'semantic')))
print(f'[DONE] RGB:{rgb_n} | Depth:{depth_n} | SemSeg:{sem_n} 帧')
print(f'[DONE] 数据路径: {OUTPUT_DIR}')
