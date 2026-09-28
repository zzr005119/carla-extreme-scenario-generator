(() => {
  "use strict";
  const player = document.getElementById("replay-player");
  if (!player) return;

  const taskPath = "/api/tasks/" + encodeURIComponent(player.dataset.taskId) + "/replay";
  const image = document.getElementById("replay-image");
  const toggle = document.getElementById("replay-toggle");
  const scrubber = document.getElementById("replay-scrubber");
  const channel = document.getElementById("replay-channel");
  const speed = document.getElementById("replay-speed");
  const status = document.getElementById("replay-status");
  const time = document.getElementById("replay-time");
  const duration = document.getElementById("replay-duration");
  const leadCar = document.getElementById("lead-car");
  const eventText = document.getElementById("replay-event");
  const eventTrack = document.getElementById("replay-event-track");
  const readouts = {
    egoSpeed: document.getElementById("replay-speed-value"),
    gap: document.getElementById("replay-gap"),
    ttc: document.getElementById("replay-ttc"),
    brake: document.getElementById("replay-brake"),
  };
  const channelLabels = {rgb: "摄像头", depth: "深度", semantic: "语义分割"};
  const eventLabels = {
    pedestrian_started: "行人开始横穿",
    pedestrian_finished: "行人完成横穿",
    lead_vehicle_brake: "前车开始急刹",
    lead_vehicle_stop_locked: "前车已停车",
    ego_safety_brake: "主车安全制动",
  };
  let replay = null;
  let timer = null;

  const numberText = (value, unit) => Number.isFinite(value) ? `${value.toFixed(1)} ${unit}` : "—";
  const frames = () => (replay && replay.channels[channel.value]) || [];
  const lastTime = () => replay.telemetry.at(-1)?.elapsed_seconds || 0;

  function pause() {
    if (timer !== null) clearInterval(timer);
    timer = null;
    toggle.textContent = "播放";
  }

  function render() {
    const selected = frames();
    if (!selected.length) return;
    const index = Math.max(0, Math.min(Number(scrubber.value), selected.length - 1));
    const frame = selected[index];
    const sample = replay.telemetry[frame.sample_index] || {};
    image.src = `${taskPath}/frame/${encodeURIComponent(channel.value)}/${encodeURIComponent(frame.name)}`;
    image.alt = `${channelLabels[channel.value]}，第 ${index + 1} 帧`;
    time.textContent = numberText(sample.elapsed_seconds, "s");
    readouts.egoSpeed.textContent = numberText(sample.ego_speed_kmh, "km/h");
    readouts.gap.textContent = numberText(sample.lead_gap_distance_m, "m");
    readouts.ttc.textContent = numberText(sample.ttc_seconds, "s");
    readouts.brake.textContent = Number.isFinite(sample.ego_control_brake)
      ? `${Math.round(sample.ego_control_brake * 100)}%` : "—";
    if (Number.isFinite(sample.lead_gap_distance_m)) {
      leadCar.style.visibility = "visible";
      leadCar.style.bottom = `${112 + Math.min(Math.max(sample.lead_gap_distance_m, 0), 50) / 50 * 140}px`;
    } else {
      leadCar.style.visibility = "hidden";
    }
    const active = [];
    if (sample.lead_braking) active.push("前车刹车");
    if (sample.pedestrian_active) active.push("行人横穿");
    if (Number.isFinite(sample.collision_count) && sample.collision_count > 0) active.push("发生碰撞");
    eventText.textContent = active.length ? active.join(" · ") : "当前无触发事件";
    status.textContent = `${index + 1} / ${selected.length} 帧`;
  }

  function resetRange(keepFraction = false) {
    const oldMaximum = Number(scrubber.max);
    const fraction = keepFraction && oldMaximum > 0 ? Number(scrubber.value) / oldMaximum : 0;
    scrubber.max = String(Math.max(0, frames().length - 1));
    scrubber.value = String(Math.round(fraction * Number(scrubber.max)));
    render();
  }

  function play() {
    if (timer !== null) return pause();
    if (Number(scrubber.value) >= Number(scrubber.max)) scrubber.value = "0";
    toggle.textContent = "暂停";
    const interval = Math.max(50, lastTime() * 1000 / Math.max(frames().length, 1) / Number(speed.value));
    timer = setInterval(() => {
      if (Number(scrubber.value) >= Number(scrubber.max)) return pause();
      scrubber.value = String(Number(scrubber.value) + 1);
      render();
    }, interval);
  }

  function markEvents() {
    eventTrack.replaceChildren();
    const total = lastTime();
    if (!total) return;
    for (const event of replay.events || []) {
      if (!Number.isFinite(event.elapsed_seconds)) continue;
      const marker = document.createElement("span");
      marker.className = "replay-event-tick";
      marker.style.left = `${Math.max(0, Math.min(100, event.elapsed_seconds / total * 100))}%`;
      marker.title = `${numberText(event.elapsed_seconds, "s")} · ${eventLabels[event.type] || event.type}`;
      eventTrack.append(marker);
    }
  }

  async function load() {
    try {
      const response = await fetch(taskPath, {headers: {Accept: "application/json"}});
      if (!response.ok) throw new Error("这次运行没有可回放的传感器帧");
      replay = await response.json();
      for (const name of ["rgb", "depth", "semantic"]) {
        if (!replay.channels[name]?.length) continue;
        const option = document.createElement("option");
        option.value = name;
        option.textContent = channelLabels[name];
        channel.append(option);
      }
      if (!channel.options.length || !replay.telemetry.length) throw new Error("回放数据不完整");
      channel.disabled = false;
      scrubber.disabled = false;
      toggle.disabled = false;
      duration.textContent = numberText(lastTime(), "s");
      markEvents();
      resetRange();
    } catch (error) {
      player.classList.add("replay-unavailable");
      status.textContent = error.message;
      image.alt = "没有可回放的画面";
    }
  }

  image.addEventListener("error", () => { status.textContent = "当前帧读取失败"; pause(); });
  toggle.addEventListener("click", play);
  scrubber.addEventListener("input", render);
  channel.addEventListener("change", () => { pause(); resetRange(true); });
  speed.addEventListener("change", () => { if (timer !== null) { pause(); play(); } });
  load();
})();
