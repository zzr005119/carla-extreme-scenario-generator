# -*- coding: utf-8 -*-
"""第一个 CARLA 自定义场景：极端天气 + 车辆传感器"""

import carla
import time
import os

# ========== 1. 连接 CARLA 服务器 ==========
client = carla.Client("localhost", 2000)
client.set_timeout(10.0)  # 10 秒超时
world = client.get_world()
print(f"✅ 已连接，当前地图: {world.get_map().name}")

# ========== 2. 设置极端天气（暴雨 + 浓雾） ==========
weather = carla.WeatherParameters(
    cloudiness=100.0,      # 云量 0~100
    precipitation=100.0,   # 降雨 0~100
    precipitation_deposits=80.0,  # 地面积水
    wind_intensity=60.0,   # 风力
    fog_density=80.0,      # 雾浓度
    fog_distance=10.0,     # 雾能见距离（米）
    sun_altitude_angle=-10.0,  # 太阳高度（负值=夜间）
)
world.set_weather(weather)
print("🌧️ 极端天气已设置：暴雨 + 浓雾 + 夜间")

# ========== 3. 生成一辆车 ==========
bp_lib = world.get_blueprint_library()
vehicle_bp = bp_lib.filter("vehicle.tesla.model3")[0]
spawn_point = world.get_map().get_spawn_points()[30]  # 选第 30 个出生点

vehicle = world.try_spawn_actor(vehicle_bp, spawn_point)
if vehicle is None:
    # 出生点被占，换个点
    for pt in world.get_map().get_spawn_points():
        vehicle = world.try_spawn_actor(vehicle_bp, pt)
        if vehicle:
            break

print(f"🚗 车辆已生成: {vehicle.type_id}")

# ========== 4. 装上 RGB 相机 ==========
camera_bp = bp_lib.find("sensor.camera.rgb")
camera_bp.set_attribute("image_size_x", "1280")
camera_bp.set_attribute("image_size_y", "720")
camera_bp.set_attribute("fov", "90")
# 相机安装在车顶正上方偏前
camera_transform = carla.Transform(carla.Location(x=1.5, z=2.4))

camera = world.spawn_actor(camera_bp, camera_transform, attach_to=vehicle)
print("📷 RGB 相机已安装")

# 保存相机图片到脚本所在目录
save_dir = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(save_dir, exist_ok=True)

def save_image(image):
    file_path = os.path.join(save_dir, f"frame_{image.frame:06d}.png")
    image.save_to_disk(file_path)
    print(f"📸 保存: {file_path}")

camera.listen(save_image)

# ========== 5. 开启自动驾驶 ==========
vehicle.set_autopilot(True)
print("🤖 自动驾驶已开启")

# ========== 6. 运行 15 秒，采集数据 ==========
print("\n⏳ 运行 15 秒，相机持续拍照...")
for i in range(15):
    time.sleep(1)
    v = vehicle.get_velocity()
    speed = 3.6 * (v.x**2 + v.y**2 + v.z**2)**0.5  # m/s -> km/h
    print(f"  [{i+1}s] 车速: {speed:.1f} km/h")

# ========== 7. 清理 ==========
print("\n🧹 清理中...")
camera.stop()
camera.destroy()
vehicle.destroy()
print(f"✅ 完成！图片保存在: {save_dir}")
