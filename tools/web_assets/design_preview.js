const panel = document.getElementById("design-preview");
const stage = document.getElementById("preview-stage");
const loadMessage = document.getElementById("preview-load");
const retry = document.getElementById("preview-retry");
const form = document.getElementById("workflow-form");
const weatherInput = document.getElementById("weather_tags");
const weatherNames = {day: "白天", night: "夜间", rain: "降雨", heavy_rain: "暴雨", fog: "雾", dense_fog: "浓雾", wet_road: "湿路", strong_wind: "大风"};
const riskNames = {low: "低风险", medium: "中风险", high: "高风险", critical: "极高风险"};
const exclusiveTags = [["day", "night"], ["rain", "heavy_rain"], ["fog", "dense_fog"]];
const choices = document.createElement("div");
choices.className = "preview-weather-options";
choices.setAttribute("role", "group");
choices.setAttribute("aria-label", "天气快捷选择");
for (const [tag, name] of Object.entries(weatherNames)) {
  const label = document.createElement("label");
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.value = tag;
  label.append(checkbox, name);
  choices.append(label);
  checkbox.addEventListener("input", () => {
    let tags = readTags().filter(value => value !== tag);
    if (checkbox.checked) {
      const exclusive = exclusiveTags.find(group => group.includes(tag)) || [];
      tags = tags.filter(value => !exclusive.includes(value));
      tags.push(tag);
    }
    weatherInput.value = tags.join(",");
    weatherInput.dispatchEvent(new Event("input", {bubbles: true}));
  });
}
weatherInput.after(choices);

function readTags() {
  return [...new Set(weatherInput.value.split(",").map(tag => tag.trim()).filter(Boolean))];
}

let setWeather = () => {};
let disposeScene = () => {};
function updateConditions() {
  const tags = readTags();
  const risk = document.getElementById("risk").value;
  const riskLabel = document.getElementById("preview-risk");
  riskLabel.textContent = riskNames[risk] || "待选择";
  riskLabel.dataset.risk = risk;
  document.getElementById("preview-weather").textContent = tags.filter(tag => weatherNames[tag]).map(tag => weatherNames[tag]).join(" · ") || "晴天示意";
  const count = document.getElementById("count");
  const model = document.getElementById("model").selectedOptions[0].textContent;
  document.getElementById("preview-request").textContent = `${model} · ${count.checkValidity() && count.value ? count.value + " 条候选" : "数量待确认"}`;
  for (const checkbox of choices.querySelectorAll("input")) checkbox.checked = tags.includes(checkbox.value);
  const unknown = tags.filter(tag => !weatherNames[tag]);
  const conflict = exclusiveTags.some(group => group.every(tag => tags.includes(tag)));
  const warning = document.getElementById("preview-warning");
  warning.textContent = unknown.length ? `未识别的天气标签：${unknown.join("、")}。` : conflict ? "天气标签有冲突，请保留一种昼夜、降雨或雾的等级。" : "";
  warning.hidden = !warning.textContent;
  setWeather(new Set(tags));
}
form.addEventListener("input", updateConditions);
form.addEventListener("change", updateConditions);
form.addEventListener("reset", () => setTimeout(updateConditions, 0));
updateConditions();
retry.addEventListener("click", () => {
  disposeScene();
  const canvas = document.getElementById("preview-canvas");
  canvas.replaceWith(canvas.cloneNode(false));
  start();
});

function unavailable(message) {
  panel.dataset.state = "error";
  loadMessage.hidden = false;
  loadMessage.textContent = message;
  retry.hidden = false;
  panel.querySelectorAll(".preview-toolbar button").forEach(button => { button.disabled = true; });
}

async function start() {
  panel.dataset.state = "loading";
  retry.hidden = true;
  loadMessage.hidden = false;
  loadMessage.textContent = "正在载入道路预览…";
  panel.querySelectorAll(".preview-toolbar button").forEach(button => { button.disabled = true; });
  const abort = new AbortController();
  let timeout;
  try {
    const [THREE, {OrbitControls}, data] = await Promise.race([
      Promise.all([
        import("three"),
        import("/static/preview/OrbitControls.js"),
        fetch("/static/preview/town10hd.json", {signal: abort.signal}).then(response => {
          if (!response.ok) throw new Error("Map unavailable");
          return response.json();
        }),
      ]),
      new Promise((_, reject) => { timeout = setTimeout(() => { abort.abort(); reject(new Error("Preview timeout")); }, 12000); }),
    ]);
    buildScene(THREE, OrbitControls, data);
  } catch (error) {
    unavailable(/WebGL|context/i.test(error.message)
      ? "浏览器无法绘制 3D，请开启硬件加速后重新加载。场景生成仍可使用。"
      : "预览资源加载失败，请重新加载预览。场景生成仍可使用。");
    console.error("Design preview:", error);
  } finally {
    clearTimeout(timeout);
  }
}

function buildScene(T, OrbitControls, data) {
  const canvas = document.getElementById("preview-canvas");
  const renderer = new T.WebGLRenderer({canvas, antialias: true, alpha: false});
  const events = new AbortController();
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = T.PCFSoftShadowMap;
  renderer.setClearColor(0xd3e0d4);
  const scene = new T.Scene();
  const origin = data.origin;
  // CARLA x/y is the ground plane; Three.js uses x/z with y pointing up.
  const position = (point, height = 0) => new T.Vector3(point[0] - origin[0], height, point[1] - origin[1]);
  const camera = new T.OrthographicCamera(-60, 60, 34, -34, 0.1, 1400);
  const controls = new OrbitControls(camera, canvas);
  controls.enableDamping = true;
  controls.minZoom = 0.55;
  controls.maxZoom = 5;
  controls.maxPolarAngle = Math.PI * 0.46;
  controls.screenSpacePanning = false;
  const materials = {
    asphalt: new T.MeshStandardMaterial({color: 0x555e61, roughness: 0.95, side: T.DoubleSide}),
    curb: new T.MeshStandardMaterial({color: 0xc8cdc7, roughness: 1, side: T.DoubleSide}),
    ground: new T.MeshStandardMaterial({color: 0xb0c4a8, roughness: 1}),
    markings: new T.LineBasicMaterial({color: 0xf2f0df}),
  };
  const ground = new T.Mesh(new T.PlaneGeometry(1600, 1600), materials.ground);
  ground.rotation.x = -Math.PI / 2;
  ground.position.y = -0.07;
  ground.receiveShadow = true;
  scene.add(ground);

  function laneMesh(points, extraWidth, height, material) {
    const vertices = [];
    const indices = [];
    for (const point of points) {
      const yaw = point[3] * Math.PI / 180;
      const half = point[4] / 2 + extraWidth;
      const dx = -Math.sin(yaw) * half;
      const dz = Math.cos(yaw) * half;
      vertices.push(point[0] - origin[0] + dx, height, point[1] - origin[1] + dz,
        point[0] - origin[0] - dx, height, point[1] - origin[1] - dz);
    }
    for (let i = 0; i < points.length - 1; i++) {
      const a = i * 2;
      indices.push(a, a + 1, a + 2, a + 1, a + 3, a + 2);
    }
    const geometry = new T.BufferGeometry();
    geometry.setAttribute("position", new T.Float32BufferAttribute(vertices, 3));
    geometry.setIndex(indices);
    geometry.computeVertexNormals();
    const mesh = new T.Mesh(geometry, material);
    mesh.receiveShadow = true;
    scene.add(mesh);
  }
  const marks = [];
  for (const lane of data.lanes) {
    laneMesh(lane.points, 0.4, -0.025, materials.curb);
    laneMesh(lane.points, 0, 0, materials.asphalt);
    if (lane.junction) continue;
    for (let i = 0; i < lane.points.length - 1; i += 3) {
      for (const point of [lane.points[i], lane.points[i + 1]]) {
        const yaw = point[3] * Math.PI / 180;
        marks.push(point[0] - origin[0] - Math.sin(yaw) * point[4] / 2, 0.035,
          point[1] - origin[1] + Math.cos(yaw) * point[4] / 2);
      }
    }
  }
  const markGeometry = new T.BufferGeometry();
  markGeometry.setAttribute("position", new T.Float32BufferAttribute(marks, 3));
  scene.add(new T.LineSegments(markGeometry, materials.markings));

  const hemi = new T.HemisphereLight(0xeef6ff, 0x64725a, 2.1);
  const sun = new T.DirectionalLight(0xfff2d4, 2.4);
  sun.position.set(-35, 80, 40);
  sun.castShadow = true;
  sun.shadow.mapSize.set(1024, 1024);
  Object.assign(sun.shadow.camera, {left: -65, right: 65, top: 65, bottom: -65});
  sun.shadow.bias = -0.001;
  scene.add(hemi, sun);

  const route = data.example_route;
  function routePoint(distance) {
    let remaining = distance;
    for (let i = 1; i < route.length; i++) {
      const a = route[i - 1], b = route[i];
      const length = Math.hypot(b[0] - a[0], b[1] - a[1]);
      if (remaining <= length) {
        const ratio = remaining / Math.max(length, 0.001);
        return [a[0] + (b[0] - a[0]) * ratio, a[1] + (b[1] - a[1]) * ratio, 0,
          Math.atan2(b[1] - a[1], b[0] - a[0]) * 180 / Math.PI];
      }
      remaining -= length;
    }
    return route[route.length - 1];
  }
  const lampMaterial = new T.MeshBasicMaterial({color: 0xfffacb});
  const brakeMaterial = new T.MeshBasicMaterial({color: 0xff4138});
  const headlights = [];
  function box(group, width, height, depth, x, y, z, material) {
    const mesh = new T.Mesh(new T.BoxGeometry(width, height, depth), material);
    mesh.position.set(x, y, z);
    mesh.castShadow = true;
    group.add(mesh);
    return mesh;
  }
  function car(point, color, braking) {
    const vehicle = new T.Group();
    const paint = new T.MeshStandardMaterial({color, roughness: 0.38, metalness: 0.15});
    const glass = new T.MeshStandardMaterial({color: 0x34444a, roughness: 0.2});
    const tire = new T.MeshStandardMaterial({color: 0x26312e});
    box(vehicle, 4.5, 0.68, 1.85, 0, 0.72, 0, paint);
    box(vehicle, 2.45, 0.62, 1.64, -0.2, 1.28, 0, glass);
    box(vehicle, 1.3, 0.06, 1.68, -0.28, 1.62, 0, paint);
    for (const x of [-1.4, 1.35]) for (const z of [-0.93, 0.93]) {
      const wheel = new T.Mesh(new T.CylinderGeometry(0.36, 0.36, 0.22, 12), tire);
      wheel.rotation.x = Math.PI / 2;
      wheel.position.set(x, 0.4, z);
      vehicle.add(wheel);
    }
    for (const z of [-0.61, 0.61]) {
      box(vehicle, 0.06, 0.22, 0.38, 2.26, 0.81, z, lampMaterial);
      box(vehicle, 0.06, 0.22, 0.38, -2.26, 0.81, z, braking ? brakeMaterial : paint);
    }
    const beamGeometry = new T.BufferGeometry().setFromPoints([
      new T.Vector3(2.3, 0.065, -0.6), new T.Vector3(15, 0.065, -3.8), new T.Vector3(15, 0.065, 3.8),
    ]);
    beamGeometry.setIndex([0, 1, 2]);
    const beam = new T.Mesh(beamGeometry, new T.MeshBasicMaterial({color: 0xfff1ad, transparent: true, opacity: 0.19, side: T.DoubleSide, depthWrite: false}));
    beam.visible = false;
    headlights.push(beam);
    vehicle.add(beam);
    vehicle.position.copy(position(point));
    vehicle.rotation.y = -point[3] * Math.PI / 180;
    scene.add(vehicle);
    return vehicle;
  }
  const ego = car(routePoint(0), 0x138f89, false);
  const lead = car(routePoint(25), 0xe7a240, true);
  const crossing = routePoint(34);
  const yaw = crossing[3] * Math.PI / 180;
  const walker = new T.Group();
  const clothes = new T.MeshStandardMaterial({color: 0xa64b79, roughness: 0.9});
  const skin = new T.MeshStandardMaterial({color: 0xd9af8d});
  const head = new T.Mesh(new T.SphereGeometry(0.25, 12, 8), skin);
  head.position.y = 1.65;
  walker.add(head);
  box(walker, 0.55, 0.65, 0.35, 0, 1.05, 0, clothes);
  for (const x of [-0.17, 0.17]) box(walker, 0.17, 0.65, 0.2, x, 0.4, 0, clothes);
  walker.position.copy(position(crossing));
  walker.position.x -= Math.sin(yaw) * 6;
  walker.position.z += Math.cos(yaw) * 6;
  scene.add(walker);
  const crossingEnd = position(crossing, 0.13);
  crossingEnd.x += Math.sin(yaw) * 3;
  crossingEnd.z -= Math.cos(yaw) * 3;
  const crossingLine = new T.Line(new T.BufferGeometry().setFromPoints([
    new T.Vector3(walker.position.x, 0.13, walker.position.z), crossingEnd,
  ]), new T.LineDashedMaterial({color: 0xc879a0, dashSize: 0.7, gapSize: 0.6}));
  crossingLine.computeLineDistances();
  scene.add(crossingLine);
  const focus = position(routePoint(17));
  const ring = new T.Mesh(new T.RingGeometry(2.7, 2.86, 48), new T.MeshBasicMaterial({color: 0x27bfac, side: T.DoubleSide}));
  ring.rotation.x = -Math.PI / 2;
  ring.position.copy(ego.position).y = 0.08;
  scene.add(ring);

  const rainValues = new Float32Array(360 * 6);
  const rainGeometry = new T.BufferGeometry();
  rainGeometry.setAttribute("position", new T.BufferAttribute(rainValues, 3));
  const rain = new T.LineSegments(rainGeometry, new T.LineBasicMaterial({color: 0xaacddd, transparent: true, opacity: 0.52, depthWrite: false}));
  rain.frustumCulled = false;
  scene.add(rain);
  const windGeometry = new T.BufferGeometry();
  const windValues = new Float32Array(40 * 6);
  windGeometry.setAttribute("position", new T.BufferAttribute(windValues, 3));
  const wind = new T.LineSegments(windGeometry, new T.LineBasicMaterial({color: 0xf1f8ea, transparent: true, opacity: 0.7}));
  wind.frustumCulled = false;
  scene.add(wind);
  let weather = new Set();
  setWeather = tags => {
    weather = tags;
    const night = tags.has("night");
    const wet = tags.has("wet_road") || tags.has("rain") || tags.has("heavy_rain");
    const fog = tags.has("fog") || tags.has("dense_fog");
    const background = night ? 0x273a42 : fog ? 0xbecbc5 : 0xd3e0d4;
    renderer.setClearColor(background);
    scene.fog = fog ? new T.Fog(background, tags.has("dense_fog") ? 35 : 60, tags.has("dense_fog") ? 150 : 240) : null;
    hemi.intensity = night ? 0.95 : 2.1;
    sun.intensity = night ? 0.55 : fog ? 1.1 : 2.4;
    sun.color.set(night ? 0xaac6ed : 0xfff2d4);
    materials.asphalt.color.set(wet ? 0x344349 : 0x555e61);
    materials.asphalt.roughness = wet ? 0.32 : 0.95;
    headlights.forEach(beam => { beam.visible = night || fog; });
    rain.visible = tags.has("rain") || tags.has("heavy_rain");
    rainGeometry.setDrawRange(0, tags.has("heavy_rain") ? 720 : 240);
    wind.visible = tags.has("strong_wind");
    panel.dataset.weather = [...tags].join(",");
  };
  let view = "perspective";
  function resetCamera(mode = view) {
    controls.enableDamping = false;
    controls.update();
    view = mode;
    camera.zoom = 1;
    controls.target.copy(focus);
    const heading = route[0][3] * Math.PI / 180;
    if (mode === "top") camera.position.set(focus.x, 110, focus.z + 0.01);
    else camera.position.set(focus.x - Math.cos(heading) * 30 + Math.sin(heading) * 46, 45,
      focus.z - Math.sin(heading) * 30 - Math.cos(heading) * 46);
    controls.enableRotate = mode !== "top";
    camera.lookAt(focus);
    camera.updateProjectionMatrix();
    controls.update();
    controls.enableDamping = true;
    for (const button of panel.querySelectorAll("[data-view]")) button.setAttribute("aria-pressed", String(button.dataset.view === mode));
    panel.dataset.view = mode;
  }
  panel.querySelectorAll("[data-view]").forEach(button => button.addEventListener("click", () => resetCamera(button.dataset.view), {signal: events.signal}));
  document.getElementById("preview-reset").addEventListener("click", () => resetCamera(), {signal: events.signal});
  canvas.addEventListener("keydown", event => {
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "+", "-", "Home"].includes(event.key)) return;
    event.preventDefault();
    if (event.key === "Home") return resetCamera();
    if (event.key === "+" || event.key === "-") {
      camera.zoom = T.MathUtils.clamp(camera.zoom * (event.key === "+" ? 1.15 : 1 / 1.15), controls.minZoom, controls.maxZoom);
      camera.updateProjectionMatrix();
    } else {
      const delta = new T.Vector3(event.key === "ArrowRight" ? 3 : event.key === "ArrowLeft" ? -3 : 0, 0,
        event.key === "ArrowDown" ? 3 : event.key === "ArrowUp" ? -3 : 0);
      camera.position.add(delta);
      controls.target.add(delta);
    }
  }, {signal: events.signal});
  const resize = new ResizeObserver(() => {
    const width = stage.clientWidth, height = stage.clientHeight;
    if (!width || !height) return;
    const half = width < 620 ? 34 : 26;
    camera.left = -half * width / height;
    camera.right = half * width / height;
    camera.top = half;
    camera.bottom = -half;
    camera.updateProjectionMatrix();
    renderer.setSize(width, height, false);
  });
  resize.observe(stage);
  const actors = [[ego, "ego"], [lead, "lead"], [walker, "ped"]].map(([actor, name]) => [actor, document.getElementById(`preview-${name}-label`)]);
  function placeLabels() {
    const occupied = [];
    for (const [actor, label] of actors) {
      const point = actor.position.clone().add(new T.Vector3(0, 3, 0)).project(camera);
      label.hidden = point.z < -1 || point.z > 1 || Math.abs(point.x) > 1 || Math.abs(point.y) > 1;
      if (label.hidden) continue;
      const width = label.offsetWidth, height = label.offsetHeight;
      const x = T.MathUtils.clamp((point.x + 1) * stage.clientWidth / 2 - width / 2, 6, stage.clientWidth - width - 6);
      let y = T.MathUtils.clamp((1 - point.y) * stage.clientHeight / 2 - height - 5, 6, stage.clientHeight - height - 40);
      for (let i = 0; i < 6; i++) {
        if (!occupied.some(rect => x < rect.x + rect.w + 4 && x + width + 4 > rect.x && y < rect.y + rect.h + 4 && y + height + 4 > rect.y)) break;
        y = Math.max(6, y - height - 5);
      }
      occupied.push({x, y, w: width, h: height});
      label.style.transform = `translate(${Math.round(x)}px, ${Math.round(y)}px)`;
    }
  }
  let onScreen = true, stopped = false, lastFrame = 0, frame;
  const visible = new IntersectionObserver(entries => { onScreen = entries[0].isIntersecting; });
  visible.observe(stage);
  const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
  function draw(now) {
    if (stopped) return;
    frame = requestAnimationFrame(draw);
    if (!onScreen || document.hidden || now - lastFrame < 32) return;
    lastFrame = now;
    controls.update();
    const time = reducedMotion.matches ? 0 : now / 1000;
    if (rain.visible) {
      for (let i = 0; i < 360; i++) {
        const n = i * 6;
        const x = focus.x + ((i * 17.37) % 100) - 50;
        const z = focus.z + ((i * 11.71) % 100) - 50;
        const y = 26 - ((i * 0.93 + time * 16) % 26);
        rainValues.set([x, y, z, x + (weather.has("strong_wind") ? 1.4 : 0.3), y - 1.2, z + 0.1], n);
      }
      rainGeometry.attributes.position.needsUpdate = true;
    }
    if (wind.visible) {
      for (let i = 0; i < 40; i++) {
        const x = focus.x + ((i * 11.7 + time * 15) % 90) - 45;
        const z = focus.z + ((i * 7.91) % 90) - 45;
        windValues.set([x, 1.5 + i % 5, z, x + 3, 1.8 + i % 5, z], i * 6);
      }
      windGeometry.attributes.position.needsUpdate = true;
    }
    renderer.render(scene, camera);
    placeLabels();
  }
  canvas.addEventListener("webglcontextlost", event => {
    event.preventDefault();
    stopped = true;
    cancelAnimationFrame(frame);
    unavailable("浏览器暂停了 3D 绘制，请重新加载预览。场景生成仍可使用。");
  }, {signal: events.signal});
  let disposed = false;
  disposeScene = () => {
    if (disposed) return;
    disposed = true;
    stopped = true;
    cancelAnimationFrame(frame);
    events.abort();
    setWeather = () => {};
    resize.disconnect();
    visible.disconnect();
    controls.dispose();
    const disposables = new Set();
    scene.traverse(object => {
      if (object.geometry) disposables.add(object.geometry);
      if (object.material) disposables.add(object.material);
    });
    disposables.forEach(item => item.dispose());
    renderer.dispose();
    if (!renderer.getContext().isContextLost()) renderer.forceContextLoss();
  };
  window.addEventListener("pagehide", event => {
    if (!event.persisted) disposeScene();
  }, {signal: events.signal});
  resetCamera();
  updateConditions();
  panel.dataset.state = "ready";
  loadMessage.hidden = true;
  panel.querySelectorAll(".preview-toolbar button").forEach(button => { button.disabled = false; });
  draw(performance.now());
}

start();
