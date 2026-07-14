# -*- coding: utf-8 -*-
"""场景02：多危险叠加 — 前车急刹 + 行人横穿 + 极端天气"""

import carla
import time
import os
import random
import math

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "..", "output", "scene_02_multi_hazard")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ==================== 1. 连接 CARLA ====================
client = carla.Client("localhost", 2000)
client.set_timeout(20.0)
world = client.get_world()
print(f"[CONNECT] 已连接 CARLA，地图: {world.get_map().name}")

# ==================== 2. 极端天气 ====================
weather = carla.WeatherParameters(
    cloudiness=100.0,
    precipitation=95.0,
    precipitation_deposits=85.0,
    wind_intensity=70.0,
    fog_density=85.0,
    fog_distance=8.0,
    sun_altitude_angle=-15.0,
    wetness=90.0,
)
world.set_weather(weather)
print("[WEATHER] 极端天气：暴雨 + 浓雾 + 夜间 + 强风")

# ==================== 3. 生成主车 (Ego Vehicle) ====================
bp_lib = world.get_blueprint_library()
ego_bp = bp_lib.filter("vehicle.tesla.model3")[0]

spawn_points = world.get_map().get_spawn_points()
ego_sp = spawn_points[40]
ego_vehicle = world.try_spawn_actor(ego_bp, ego_sp)
if ego_vehicle is None:
    for pt in spawn_points:
        ego_vehicle = world.try_spawn_actor(ego_bp, pt)
        if ego_vehicle:
            ego_sp = pt
            break

print(f"[EGO] 主车已生成: {ego_vehicle.type_id} @ spawn {spawn_points.index(ego_sp)}")

# ==================== 4. 主车装 RGB 相机 ====================
camera_bp = bp_lib.find("sensor.camera.rgb")
camera_bp.set_attribute("image_size_x", "1280")
camera_bp.set_attribute("image_size_y", "720")
camera_bp.set_attribute("fov", "90")
camera_tf = carla.Transform(carla.Location(x=1.5, z=2.4))

ego_camera = world.spawn_actor(camera_bp, camera_tf, attach_to=ego_vehicle)
print("[CAMERA] RGB 相机已安装（主车）")

frame_count = [0]

def save_image(image):
    frame_count[0] += 1
    fname = os.path.join(OUTPUT_DIR, f"frame_{image.frame:06d}.png")
    image.save_to_disk(fname)

ego_camera.listen(save_image)

# ==================== 5. 生成前车 (Lead Vehicle) ====================
lead_bp = bp_lib.filter("vehicle.audi.a2")[0]

# 在主车前方约 25 米同向生成
ego_loc = ego_sp.location
ego_rot = ego_sp.rotation
yaw_rad = math.radians(ego_rot.yaw)
lead_x = ego_loc.x + 25 * math.cos(yaw_rad)
lead_y = ego_loc.y + 25 * math.sin(yaw_rad)
lead_sp = carla.Transform(
    carla.Location(x=lead_x, y=lead_y, z=ego_loc.z),
    ego_rot
)

lead_vehicle = world.try_spawn_actor(lead_bp, lead_sp)
if lead_vehicle is None:
    # fallback: 往前搜索附近的 spawn point
    for pt in spawn_points:
        if pt.location.distance(ego_loc) > 20:
            lead_vehicle = world.try_spawn_actor(lead_bp, pt)
            if lead_vehicle:
                lead_sp = pt
                break

print(f"[LEAD] 前车已生成: {lead_vehicle.type_id}" if lead_vehicle else "[LEAD] 前车生成失败！")

# ==================== 6. 生成行人 (Walker) ====================
walker_bp = bp_lib.filter("walker.pedestrian.0007")[0]  # 女性行人
walker_sp = carla.Transform(
    carla.Location(
        x=ego_loc.x + 35 * math.cos(yaw_rad) - 5 * math.sin(yaw_rad),
        y=ego_loc.y + 35 * math.sin(yaw_rad) + 5 * math.cos(yaw_rad),
        z=ego_loc.z
    )
)

walker = world.try_spawn_actor(walker_bp, walker_sp)

if walker:
    controller_bp = bp_lib.find("controller.ai.walker")
    walker_controller = world.spawn_actor(controller_bp, carla.Transform(), attach_to=walker)
    walker_controller.start()

    # 行人目标：横穿马路（从左到右）
    cross_x = walker_sp.location.x + 10 * math.sin(yaw_rad)
    cross_y = walker_sp.location.y - 10 * math.cos(yaw_rad)
    walker_dest = carla.Location(x=cross_x, y=cross_y, z=walker_sp.location.z)
    walker_controller.go_to_location(walker_dest)
    walker_controller.set_max_speed(1.5)  # 慢走
    print(f"[WALKER] 行人已生成，正在横穿马路")
else:
    walker_controller = None
    print("[WALKER] 行人生成失败，跳过")

# ==================== 7. 设置自动驾驶 + 场景时序 ====================
ego_vehicle.set_autopilot(True)
if lead_vehicle:
    lead_vehicle.set_autopilot(True)
print("[AUTOPILOT] 两车自动驾驶已开启")

print("\n" + "="*50)
print("  场景开始运行")
print("  [0-5s]   正常跟车行驶")
print("  [5s]     前车急刹！")
print("  [3-10s]  行人横穿马路")
print("  [0-20s]  相机持续拍照")
print("="*50 + "\n")

start_time = time.time()
brake_triggered = False
walker_active = False

try:
    for step in range(20):
        time.sleep(1)
        elapsed = step + 1

        # 主车状态
        ego_v = ego_vehicle.get_velocity()
        ego_speed = 3.6 * math.sqrt(ego_v.x**2 + ego_v.y**2 + ego_v.z**2)

        # 前车距离
        if lead_vehicle:
            lead_loc = lead_vehicle.get_location()
            dist = ego_vehicle.get_location().distance(lead_loc)
        else:
            dist = float("inf")

        status = f"  [{elapsed:2d}s] 主车: {ego_speed:5.1f} km/h | 距前车: {dist:5.1f} m"

        # 5 秒时触发前车急刹
        if elapsed == 5 and lead_vehicle and not brake_triggered:
            lead_vehicle.apply_control(carla.VehicleControl(throttle=0.0, brake=1.0))
            brake_triggered = True
            status += " ⚠️ 前车急刹！！"

        # 行人激活（第 3 秒开始横穿）
        if elapsed == 3 and walker_controller and not walker_active:
            walker_active = True
            status += " 🚶 行人开始横穿！"

        print(status)

        # 碰撞检测
        if lead_vehicle:
            if dist < 1.5:
                print("  💥 碰撞！主车追尾前车！")
                break

except KeyboardInterrupt:
    print("\n[STOP] 用户中断")

# ==================== 8. 清理 ====================
print("\n[CLEANUP] 清理所有 actor...")

# 先停相机
ego_camera.stop()

# 销毁顺序：控制器 → 行人 → 车辆 → 相机
actors_to_destroy = []
if walker_controller:
    actors_to_destroy.append(walker_controller)
if walker:
    actors_to_destroy.append(walker)
if lead_vehicle:
    actors_to_destroy.append(lead_vehicle)
if ego_vehicle:
    actors_to_destroy.append(ego_vehicle)
actors_to_destroy.append(ego_camera)

for actor in actors_to_destroy:
    try:
        actor.destroy()
    except:
        pass

total_frames = frame_count[0]
print(f"[DONE] 场景结束，共采集 {total_frames} 帧")
print(f"[DONE] 数据保存在: {OUTPUT_DIR}")
