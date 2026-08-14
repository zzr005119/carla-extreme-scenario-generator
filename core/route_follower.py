"""确定性 waypoint 路线跟踪控制。"""

import math

import carla


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def speed_mps(velocity):
    return math.sqrt(velocity.x ** 2 + velocity.y ** 2 + velocity.z ** 2)


def distance_2d(first, second):
    return math.hypot(first.x - second.x, first.y - second.y)


def apply_brake_override(control, brake):
    control.throttle = 0.0
    control.brake = max(float(control.brake), clamp(float(brake), 0.0, 1.0))
    return control


class DeterministicRouteFollower:
    """使用纯追踪转向和速度 PID 沿固定 waypoint 序列控制车辆。"""

    def __init__(
        self,
        vehicle,
        route_waypoints,
        fixed_delta_seconds,
        start_index=0,
        target_speed_kmh=29.0,
        lookahead_m=6.0,
        steering_gain=1.35,
        maximum_steer=0.8,
        maximum_steer_delta=0.1,
        speed_kp=0.45,
        speed_ki=0.05,
        speed_kd=0.02,
        maximum_throttle=0.75,
        maximum_brake=1.0,
        search_window_points=40,
    ):
        if not route_waypoints:
            raise ValueError("route_waypoints 不能为空")
        if fixed_delta_seconds <= 0:
            raise ValueError("fixed_delta_seconds 必须大于 0")
        if target_speed_kmh <= 0:
            raise ValueError("target_speed_kmh 必须大于 0")
        if lookahead_m <= 0:
            raise ValueError("lookahead_m 必须大于 0")

        self.vehicle = vehicle
        self.route_waypoints = list(route_waypoints)
        self.route_locations = [
            waypoint.transform.location for waypoint in self.route_waypoints
        ]
        self.fixed_delta_seconds = float(fixed_delta_seconds)
        self.start_index = clamp(
            int(start_index),
            0,
            len(self.route_locations) - 1,
        )
        self.progress_index = self.start_index
        self.target_index = self.start_index
        self.target_speed_kmh = float(target_speed_kmh)
        self.lookahead_m = float(lookahead_m)
        self.steering_gain = float(steering_gain)
        self.maximum_steer = float(maximum_steer)
        self.maximum_steer_delta = float(maximum_steer_delta)
        self.speed_kp = float(speed_kp)
        self.speed_ki = float(speed_ki)
        self.speed_kd = float(speed_kd)
        self.maximum_throttle = float(maximum_throttle)
        self.maximum_brake = float(maximum_brake)
        self.search_window_points = max(4, int(search_window_points))
        self.speed_error_integral = 0.0
        self.previous_speed_error = None
        self.previous_steer = 0.0

    def reset_speed_controller(self):
        self.speed_error_integral = 0.0
        self.previous_speed_error = None

    def nearest_route_index(self, location):
        search_start = max(self.start_index, self.progress_index - 4)
        search_end = min(
            len(self.route_locations),
            self.progress_index + self.search_window_points + 1,
        )
        nearest_index = min(
            range(search_start, search_end),
            key=lambda index: distance_2d(location, self.route_locations[index]),
        )
        self.progress_index = max(self.progress_index, nearest_index)
        return self.progress_index

    def lookahead_route_index(self, location):
        route_index = self.nearest_route_index(location)
        target_index = route_index
        accumulated_distance = distance_2d(
            location,
            self.route_locations[route_index],
        )
        while (
            target_index + 1 < len(self.route_locations)
            and accumulated_distance < self.lookahead_m
        ):
            accumulated_distance += distance_2d(
                self.route_locations[target_index],
                self.route_locations[target_index + 1],
            )
            target_index += 1
        self.target_index = target_index
        return target_index

    def steering_control(self, transform, target_location):
        forward = transform.get_forward_vector()
        target_x = target_location.x - transform.location.x
        target_y = target_location.y - transform.location.y
        target_norm = math.hypot(target_x, target_y)
        if target_norm <= 1e-6:
            desired_steer = 0.0
        else:
            target_x /= target_norm
            target_y /= target_norm
            dot = clamp(forward.x * target_x + forward.y * target_y, -1.0, 1.0)
            cross_z = forward.x * target_y - forward.y * target_x
            heading_error = math.atan2(cross_z, dot)
            desired_steer = clamp(
                self.steering_gain * heading_error,
                -self.maximum_steer,
                self.maximum_steer,
            )
        steer_change = clamp(
            desired_steer - self.previous_steer,
            -self.maximum_steer_delta,
            self.maximum_steer_delta,
        )
        self.previous_steer = clamp(
            self.previous_steer + steer_change,
            -self.maximum_steer,
            self.maximum_steer,
        )
        return self.previous_steer

    def longitudinal_control(self, current_speed_mps, target_speed_kmh):
        target_speed_mps = float(target_speed_kmh) / 3.6
        speed_error = target_speed_mps - current_speed_mps
        if (
            self.previous_speed_error is not None
            and speed_error * self.previous_speed_error < 0
        ):
            self.speed_error_integral = 0.0
        self.speed_error_integral = clamp(
            self.speed_error_integral
            + speed_error * self.fixed_delta_seconds,
            -5.0,
            5.0,
        )
        speed_derivative = (
            0.0
            if self.previous_speed_error is None
            else (speed_error - self.previous_speed_error)
            / self.fixed_delta_seconds
        )
        self.previous_speed_error = speed_error
        acceleration = (
            self.speed_kp * speed_error
            + self.speed_ki * self.speed_error_integral
            + self.speed_kd * speed_derivative
        )
        if acceleration >= 0:
            return clamp(acceleration, 0.0, self.maximum_throttle), 0.0
        return 0.0, clamp(-acceleration, 0.0, self.maximum_brake)

    def run_step(self, target_speed_kmh=None):
        transform = self.vehicle.get_transform()
        velocity = self.vehicle.get_velocity()
        current_speed_mps = speed_mps(velocity)
        target_index = self.lookahead_route_index(transform.location)
        target_location = self.route_locations[target_index]
        steer = self.steering_control(transform, target_location)
        effective_target_speed = (
            self.target_speed_kmh
            if target_speed_kmh is None
            else float(target_speed_kmh)
        )
        if (
            target_index == len(self.route_locations) - 1
            and distance_2d(transform.location, target_location) <= 2.0
        ):
            effective_target_speed = 0.0
        throttle, brake = self.longitudinal_control(
            current_speed_mps,
            effective_target_speed,
        )
        control = carla.VehicleControl(
            throttle=throttle,
            steer=steer,
            brake=brake,
            hand_brake=False,
            manual_gear_shift=False,
        )
        return control, {
            "progress_index": self.progress_index,
            "target_index": self.target_index,
            "target_speed_kmh": effective_target_speed,
            "current_speed_kmh": current_speed_mps * 3.6,
        }
