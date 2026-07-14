# -*- coding: utf-8 -*-
"""场景03：多传感器集成 — RGB + Depth + Semantic Segmentation + 多危险叠加"""

import carla
import time
import os
import math
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "..", "output", "scene_03_multi_sensor")
for sub in ["rgb", "depth", "semantic"]:
    os.makedirs(os.path.join(OUTPUT_DIR, sub), exist_ok=True)

# ==================== 1. 连接 CARLA ====================
client = carla.Client("localhost", 2000)
client.set_timeout(20.0)
world = client.get_world()
print(f"[CONNECT] CARLA 地图: {world.get_map().name}")

# ==================== 2. 极端天气 ====================
weather = carla.WeatherParameters(
    cloudiness=100.0, precipitation=95.0,
    precipitation_deposits=85.0, wind_intensity=70.0,
    fog_density=85.0, fog_distance=8.0,
    sun_altitude_angle=-15.0, wetness=90.0,
)
world.set_weather(weather)
print("[WEATHER] 暴雨 + 浓雾 + 夜间")

# ==================== 3. 生成主车 ====================
bp_lib = world.get_blueprint_library()
ego_bp = bp_lib.filter("vehicle.tesla.model3")[0]
spawn_points = world.get_map().get_spawn_points()
ego_sp = spawn_points[40]
ego_vehicle = world.try_spawn_actor(ego_bp, ego_sp)
if not ego_vehicle:
    for pt in spawn_points:
        ego_vehicle = world.try_spawn_actor(ego_bp, pt)
        if ego_vehicle:
            ego_sp = pt
            break
print(f"[EGO] {ego_vehicle.type_id}")

# ==================== 4. 传感器安装 ====================
SENSOR_POS = carla.Transform(carla.Location(x=1.5, z=2.4))

# 4a. RGB 相机
rgb_bp = bp_lib.find("sensor.camera.rgb")
rgb_bp.set_attribute("image_size_x", "1280")
rgb_bp.set_attribute("image_size_y", "720")
rgb_bp.set_attribute("fov", "90")
rgb_cam = world.spawn_actor(rgb_bp, SENSOR_POS, attach_to=ego_vehicle)

# 4b. 深度相机
depth_bp = bp_lib.find("sensor.camera.depth")
depth_bp.set_attribute("image_size_x", "1280")
depth_bp.set_attribute("image_size_y", "720")
depth_bp.set_attribute("fov", "90")
depth_cam = world.spawn_actor(depth_bp, SENSOR_POS, attach_to=ego_vehicle)

# 4c. 语义分割相机
sem_bp = bp_lib.find("sensor.camera.semantic_segmentation")
sem_bp.set_attribute("image_size_x", "1280")
sem_bp.set_attribute("image_size_y", "720")
sem_bp.set_attribute("fov", "90")
sem_cam = world.spawn_actor(sem_bp, SENSOR_POS, attach_to=ego_vehicle)

print("[SENSORS] RGB + Depth + SemanticSeg 已安装")

# ---- 帧计数器 ----
frame_count = [0]

# ==================== 5. 传感器回调 ====================

def save_rgb(image):
    image.save_to_disk(os.path.join(OUTPUT_DIR, "rgb", f"frame_{image.frame:06d}.png"))

def save_depth(image):
    """解码深度图并保存为灰度 PNG"""
    # CARLA depth 数据: (H,W,4) BGRA，深度编码在 RGB 通道
    data = np.frombuffer(image.raw_data, dtype=np.uint8)
    data = data.reshape((image.height, image.width, 4))
    # 解码: depth_m = (R + G*256 + B*65536) / (2^24 - 1) * 1000
    depth_m = (data[:,:,2].astype(np.float32) +
               data[:,:,1].astype(np.float32) * 256 +
               data[:,:,0].astype(np.float32) * 65536) / 16777215.0 * 1000.0
    # 归一化到 0-255 保存为灰度图
    depth_gray = np.clip(depth_m / 100.0 * 255, 0, 255).astype(np.uint8)
    from PIL import Image
    img = Image.fromarray(depth_gray, mode="L")
    img.save(os.path.join(OUTPUT_DIR, "depth", f"frame_{image.frame:06d}.png"))

def save_semantic(image):
    """语义分割 — 应用 CityScapes 调色板后保存"""
    # 标签 -> 颜色映射 (CityScapes 子集)
    TAG_COLORS = {
        0:  (0,   0,   0),     # 未标注
        1:  (128, 64,  128),   # 道路
        4:  (220, 20,  60),    # 行人
        6:  (157, 234, 50),    # 护栏
        7:  (128, 64,  128),   # 车道线
        10: (0,   0,   142),   # 车辆
        12: (220, 220, 0),     # 交通标志
        13: (70,  130, 180),   # 天空
        14: (81,  0,   81),    # 地面
        22: (107, 142, 35),    # 地形
    }

    image.convert(carla.ColorConverter.CityScapesPalette)
    image.save_to_disk(os.path.join(OUTPUT_DIR, "semantic", f"frame_{image.frame:06d}.png"))

    # 同时保存原始标签数据（numpy）
    data = np.frombuffer(image.raw_data, dtype=np.uint8)
    data = data.reshape((image.height, image.width, 4))
    labels = data[:, :, 2]  # R 通道就是 tag ID
    np.save(
        os.path.join(OUTPUT_DIR, "semantic", f"labels_{image.frame:06d}.npy"),
        labels
    )

rgb_cam.listen(save_rgb)
depth_cam.listen(save_depth)
sem_cam.listen(save_semantic)
print("[CALLBACK] 三路传感器回调已注册")

# ==================== 6. 前车 ====================
lead_bp = bp_lib.filter("vehicle.audi.a2")[0]
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
print(f"[LEAD] 前车: {lead_vehicle.type_id}" if lead_vehicle else "[LEAD] 失败")

# ==================== 7. 行人 ====================
walker_bp = bp_lib.filter("walker.pedestrian.0007")[0]
walker_loc = carla.Location(
    x=ego_sp.location.x + 35 * math.cos(yaw_rad) - 5 * math.sin(yaw_rad),
    y=ego_sp.location.y + 35 * math.sin(yaw_rad) + 5 * math.cos(yaw_rad),
    z=ego_sp.location.z
)
walker = world.try_spawn_actor(walker_bp, carla.Transform(walker_loc))
walker_ctrl = None
if walker:
    ctrl_bp = bp_lib.find("controller.ai.walker")
    walker_ctrl = world.spawn_actor(ctrl_bp, carla.Transform(), attach_to=walker)
    walker_ctrl.start()
    dest = carla.Location(
        x=walker_loc.x + 10 * math.sin(yaw_rad),
        y=walker_loc.y - 10 * math.cos(yaw_rad),
        z=walker_loc.z
    )
    walker_ctrl.go_to_location(dest)
    walker_ctrl.set_max_speed(1.5)
    print("[WALKER] 行人横穿中")
else:
    print("[WALKER] 失败")

# ==================== 8. 运行场景 ====================
ego_vehicle.set_autopilot(True)
if lead_vehicle:
    lead_vehicle.set_autopilot(True)

print("\n" + "="*50)
print("  多传感器场景运行中 (20s)")
print("  RGB     → output/rgb/")
print("  Depth   → output/depth/ (灰度, 0=近 255=100m+)")
print("  SemSeg  → output/semantic/ (CityScapes 着色 + .npy 标签)")
print("  第 5s 前车急刹 | 第 3s 行人横穿")
print("="*50 + "\n")

brake_done = False
try:
    for step in range(20):
        time.sleep(1)
        t = step + 1

        ego_v = ego_vehicle.get_velocity()
        speed = 3.6 * math.sqrt(ego_v.x**2 + ego_v.y**2 + ego_v.z**2)
        dist = lead_vehicle.get_location().distance(ego_vehicle.get_location()) if lead_vehicle else float("inf")

        msg = f"  [{t:2d}s] 速度:{speed:5.1f}km/h | 车距:{dist:5.1f}m"

        if t == 5 and lead_vehicle and not brake_done:
            lead_vehicle.apply_control(carla.VehicleControl(throttle=0.0, brake=1.0))
            brake_done = True
            msg += " ⚠️急刹！"
        if t == 3 and walker_ctrl:
            msg += " 🚶行人！"

        print(msg)
        if lead_vehicle and dist < 1.5:
            print("  💥 碰撞！")
            break

except KeyboardInterrupt:
    print("\n[STOP] 用户中断")

# ==================== 9. 清理 ====================
print("\n[CLEANUP]")
for s in [rgb_cam, depth_cam, sem_cam]:
    s.stop()

for a in [walker_ctrl, walker, lead_vehicle, ego_vehicle, rgb_cam, depth_cam, sem_cam]:
    try:
        a.destroy() if a else None
    except:
        pass

# 统计
rgb_n = len(os.listdir(os.path.join(OUTPUT_DIR, "rgb")))
depth_n = len(os.listdir(os.path.join(OUTPUT_DIR, "depth")))
sem_n = len(os.listdir(os.path.join(OUTPUT_DIR, "semantic")))
print(f"[DONE] RGB:{rgb_n} | Depth:{depth_n} | SemSeg:{sem_n} 帧")
print(f"[DONE] 数据路径: {OUTPUT_DIR}")
