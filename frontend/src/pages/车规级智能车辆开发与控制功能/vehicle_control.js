const API_BASE = "";

const ROUTE_LABELS = {
    SEM_10M_BUILDING_LOOP: "经管学院 10m 外侧环线",
    NAVIGATION_WAYPOINTS_LATEST: "HIL导航路点 YAML 路线",
    HOLD_POSITION: "当前位置保持"
};

let nativeHilUrl = "http://10.8.129.232:5173/%E3%80%81";
let nativeHilFrameAttached = false;

const state = {
    health: null,
    map: null,
    route: null,
    navigation: null,
    pointcloud: null,
    pointcloudImage: null,
    cars: [],
    activeCar: null,
    vehicle: null,
    commands: [],
    trajectory: [],
    polling: null,
    draw: {
        pointcloud: true,
        route: true,
        vehicle: true
    },
    projection: null
};

document.addEventListener("DOMContentLoaded", async () => {
    bindEvents();
    updateSpeedDisplay();
    await initialize();
});

function bindEvents() {
    qs("backBtn").addEventListener("click", () => window.history.back());
    qs("refreshBtn").addEventListener("click", refreshAll);
    qs("startNativeHilBtn").addEventListener("click", startNativeHil);
    qs("startNativeHilBtnInline").addEventListener("click", startNativeHil);
    qs("openNativeHilBtn").addEventListener("click", () => {
        window.open(nativeHilUrl, "_blank", "noopener");
        attachNativeHilFrame();
        pollNativeHilStatus(4);
    });
    document.querySelectorAll("[data-view]").forEach(button => {
        button.addEventListener("click", () => setActiveView(button.dataset.view));
    });
    qs("targetSpeed").addEventListener("input", () => {
        qs("speedSlider").value = qs("targetSpeed").value;
        qs("sliderValue").textContent = Number(qs("targetSpeed").value || 0).toFixed(1);
        updateSpeedDisplay();
    });
    qs("speedSlider").addEventListener("input", () => {
        qs("sliderValue").textContent = Number(qs("speedSlider").value || 0).toFixed(1);
    });
    qs("carSelect").addEventListener("change", () => {
        state.activeCar = state.cars.find(car => String(car.id) === qs("carSelect").value) || state.cars[0];
        drawMap();
    });
    qs("routeSelect").addEventListener("change", async () => {
        await loadRoute();
        drawMap();
    });
    qs("startMqttBtn").addEventListener("click", startMqtt);
    qs("sendRouteBtn").addEventListener("click", sendRoute);
    qs("startSimBtn").addEventListener("click", startSimulation);
    qs("stopSimBtn").addEventListener("click", stopSimulation);
    qs("resetBtn").addEventListener("click", resetExperiment);
    qs("sendGoalBtn").addEventListener("click", sendGoalNode);
    qs("applySpeedBtn").addEventListener("click", applySliderSpeed);

    document.querySelectorAll(".cmd-btn").forEach(button => {
        button.addEventListener("click", () => {
            const speeds = { crawl: 0.6, normal: 1.2, fast: 2.4 };
            const cmd = button.dataset.cmd;
            if (cmd === "emergency") {
                sendCommand("EMERGENCY_STOP", { action: "emergency", safetyAction: "controlled_stop" });
            } else {
                const speed = speeds[cmd] ?? 1.2;
                qs("targetSpeed").value = speed;
                qs("speedSlider").value = speed;
                qs("sliderValue").textContent = speed.toFixed(1);
                updateSpeedDisplay();
                sendCommand("SET_SPEED", { action: "set_speed", speed });
            }
        });
    });

    [
        ["togglePointcloud", "pointcloud"],
        ["toggleRoute", "route"],
        ["toggleVehicle", "vehicle"]
    ].forEach(([id, key]) => {
        qs(id).addEventListener("click", event => {
            state.draw[key] = !state.draw[key];
            event.currentTarget.classList.toggle("active", state.draw[key]);
            drawMap();
        });
    });

    window.addEventListener("resize", drawMap);
}

async function initialize() {
    setStatus("加载HIL项目资源...");
    try {
        const [health, map, navigation, pointcloud] = await Promise.all([
            apiGet("/api/vehicle-control/health"),
            apiGet("/api/vehicle-control/maps/default"),
            apiGet("/api/vehicle-control/navigation-waypoints"),
            apiGet("/api/vehicle-control/pointcloud-layer")
        ]);
        state.health = health;
        if (health.native) updateNativeHilFrame(health.native);
        state.map = map;
        state.navigation = navigation.route;
        state.pointcloud = pointcloud.layer;
        await loadPointcloudImage();
        await loadRoute();
        await refreshAll();
        startPolling();
        setServerStatus(true, "服务器: HIL接口已连接");
        setStatus("HIL资源已就绪");
        markStepDone("startMqttBtn", false);
    } catch (error) {
        setServerStatus(false, "服务器: HIL接口未连接");
        setStatus("接口加载失败");
        console.error(error);
    }
}

function updateNativeHilFrame(native) {
    const frame = qs("nativeHilFrame");
    const status = qs("nativeHilStatus");
    if (native && native.url) nativeHilUrl = native.url;
    if (frame && nativeHilFrameAttached && frame.getAttribute("src") !== nativeHilUrl) frame.src = nativeHilUrl;
    const frontendReady = !!(native && native.frontend_ready);
    const backendReady = !!(native && native.backend_ready);
    const starting = !!(native && native.starting);
    if (frontendReady && backendReady) {
        status.textContent = `HIL 原生完整服务已连接：${nativeHilUrl}`;
    } else if (frontendReady) {
        status.textContent = `HIL 原生前端已连接，后端待就绪：${nativeHilUrl}`;
    } else if (starting) {
        status.textContent = "HIL 原生服务正在后台启动，页面已打开，稍后自动连接";
    } else {
        status.textContent = "HIL 原生界面未启动，可点击启动/连接";
    }
    status.classList.toggle("online", frontendReady && backendReady);
    status.classList.toggle("partial", frontendReady && !backendReady);
}

function attachNativeHilFrame() {
    const frame = qs("nativeHilFrame");
    if (!frame) return;
    nativeHilFrameAttached = true;
    if (frame.getAttribute("src") !== nativeHilUrl) frame.src = nativeHilUrl;
}

async function loadNativeHilStatus() {
    try {
        const native = await apiGet("/api/vehicle-control/native/status");
        updateNativeHilFrame(native);
    } catch {
        updateNativeHilFrame({ url: nativeHilUrl, frontend_ready: false });
    }
}

function pollNativeHilStatus(times, delay) {
    const remaining = Number(times || 1);
    const wait = Number(delay || 1400);
    if (remaining <= 0) return;
    setTimeout(() => {
        loadNativeHilStatus();
        pollNativeHilStatus(remaining - 1, Math.min(wait + 400, 3000));
    }, wait);
}

async function startNativeHil() {
    window.open(nativeHilUrl, "_blank", "noopener");
    attachNativeHilFrame();
    qs("nativeHilStatus").textContent = "已打开 HIL 原生页面，正在后台启动/连接...";
    try {
        const native = await apiPost("/api/vehicle-control/native/start", {});
        updateNativeHilFrame(native);
        setStatus(native.message || "HIL 原生服务启动命令已发送");
        pollNativeHilStatus(8);
    } catch (error) {
        setStatus(`HIL 原生服务启动失败：${error.message}`);
        pollNativeHilStatus(3);
    }
}

async function refreshAll() {
    await Promise.all([loadCars(), loadVehicleState(), loadCommands(), loadFiles()]);
    renderStatusCards();
    renderTopics();
    renderCommands();
    renderFleet();
    drawMap();
}

async function loadCars() {
    state.cars = await apiGet("/api/vehicle-control/cars");
    const select = qs("carSelect");
    const selected = select.value;
    select.innerHTML = state.cars.map(car => `
        <option value="${car.id}">${car.carName} (${car.carCode}, ${car.communicationProtocol})</option>
    `).join("");
    if (selected && state.cars.some(car => String(car.id) === selected)) {
        select.value = selected;
    }
    state.activeCar = state.cars.find(car => String(car.id) === select.value) || state.cars[0] || null;
    renderFleet();
}

async function loadRoute() {
    const routeCode = qs("routeSelect").value;
    state.route = await apiGet(`/api/vehicle-control/maps/DLUT-SEM-CAMPUS/route?route_code=${encodeURIComponent(routeCode)}`);
    qs("mapRouteName").textContent = routeCode;
    qs("mapScale").textContent = `${Math.round(state.route.totalLengthM || 0)} m / ${state.route.waypointCount || 0} points`;
}

async function loadVehicleState() {
    state.vehicle = await apiGet("/api/vehicle-control/vehicle-state");
    if (state.vehicle.active_car) {
        state.activeCar = state.vehicle.active_car;
    }
    updateVehicleDisplay(state.vehicle);
}

async function loadCommands() {
    state.commands = await apiGet("/api/vehicle-control/commands/recent?limit=8");
}

async function loadFiles() {
    try {
        const data = await apiGet("/api/vehicle-control/trajectory-files");
        renderFiles(data.files || []);
    } catch {
        renderFiles([]);
    }
}

async function loadPointcloudImage() {
    if (!state.pointcloud || !state.pointcloud.image) return;
    const image = new Image();
    image.decoding = "async";
    image.src = state.pointcloud.image;
    await new Promise((resolve, reject) => {
        image.onload = resolve;
        image.onerror = reject;
    });
    state.pointcloudImage = image;
}

async function startMqtt() {
    setStatus("正在启动HIL通信...");
    const enable = qs("enableMqtt").checked;
    const data = await apiPost("/api/vehicle-control/start-mqtt", { enable });
    markStepDone("startMqttBtn");
    setStatus(data.connected ? "MQTT桥接已连接" : "本地HIL通道已启用");
    await refreshAll();
}

async function sendRoute() {
    const routeCode = qs("routeSelect").value;
    const routeMode = qs("routeMode").value;
    const carId = activeCarId();
    await sendCommand("SET_ROUTE", {
        action: "set_route",
        routeCode,
        routeMode,
        routeSource: "server_verified_hil_route",
        mapCode: "DLUT-SEM-CAMPUS",
        executionMode: "vehicle_local_planner"
    }, carId);
    markStepDone("sendRouteBtn");
}

async function startSimulation() {
    setStatus("正在启动HIL闭环实验...");
    state.trajectory = [];
    const payload = {
        carId: activeCarId(),
        routeCode: qs("routeSelect").value,
        routeMode: qs("routeMode").value,
        speed: Number(qs("targetSpeed").value || 1.2),
        mqtt: qs("enableMqtt").checked,
        duration: 300
    };
    const data = await apiPost("/api/vehicle-control/start-simulation", payload);
    markStepDone("startSimBtn");
    setStatus(data.message || "HIL闭环实验运行中");
    startPolling();
    await refreshAll();
}

async function stopSimulation() {
    await apiPost("/api/vehicle-control/stop-simulation", {});
    markStepDone("stopSimBtn");
    setStatus("已安全停车");
    await refreshAll();
}

async function resetExperiment() {
    await apiPost("/api/vehicle-control/reset", {});
    state.trajectory = [];
    ["startMqttBtn", "sendRouteBtn", "startSimBtn", "stopSimBtn"].forEach(id => markStepDone(id, false));
    setStatus("已重置");
    await refreshAll();
}

async function sendGoalNode() {
    const nodeId = Number(qs("goalNodeInput").value || 0);
    const data = await apiPost("/api/vehicle-control/road-topology/goal-node", { nodeId });
    qs("goalStatus").textContent = data.message || `目标节点 ${nodeId} 已下发`;
    await refreshAll();
}

async function applySliderSpeed() {
    const speed = Number(qs("speedSlider").value || 0);
    qs("targetSpeed").value = speed;
    updateSpeedDisplay();
    await sendCommand("SET_SPEED", { action: "set_speed", speed });
}

async function sendCommand(commandType, payload, carId = activeCarId()) {
    const command = await apiPost(`/api/vehicle-control/cars/${carId}/commands`, { commandType, payload });
    state.commands = [command, ...state.commands].slice(0, 8);
    renderCommands();
    await loadVehicleState();
    return command;
}

function startPolling() {
    if (state.polling) clearInterval(state.polling);
    state.polling = setInterval(async () => {
        try {
            await loadVehicleState();
            await loadCommands();
            renderStatusCards();
            renderTopics();
            renderCommands();
            drawMap();
            if (state.vehicle && ["completed", "stopped"].includes(state.vehicle.status)) {
                await loadFiles();
            }
        } catch (error) {
            console.warn("polling failed", error);
        }
    }, 800);
}

function updateVehicleDisplay(data) {
    if (!data) return;
    qs("positionDisplay").textContent = `${fmt(data.x, 1)}, ${fmt(data.y, 1)}`;
    qs("currentSpeedDisplay").textContent = `${fmt(data.speed, 2)} m/s`;
    qs("headingDisplay").textContent = `${fmt(data.angle, 1)} deg`;
    qs("edgeDisplay").textContent = data.current_edge || "--";
    qs("junctionDistDisplay").textContent = `${fmt(data.dist_to_junction, 1)} m`;
    qs("nextEdgeDisplay").textContent = `${data.next_edge || "--"} / ${data.turn_direction || "--"}`;
    qs("geoDisplay").textContent = data.longitude && data.latitude
        ? `${Number(data.longitude).toFixed(6)}, ${Number(data.latitude).toFixed(6)}`
        : "--, --";
    qs("distanceDisplay").textContent = `${fmt(data.battery_percent, 1)}% / ${fmt(data.distance, 1)} m`;
    qs("simStep").textContent = data.step ?? 0;

    if (data.active_car && qs("carSelect").value !== String(data.active_car.id)) {
        qs("carSelect").value = String(data.active_car.id);
    }

    if (data.step !== undefined && data.running) {
        const row = {
            step: data.step,
            time: (data.step * 0.1).toFixed(1),
            x: data.x,
            y: data.y,
            speed: data.speed,
            angle: data.angle,
            edge: data.current_edge
        };
        if (!state.trajectory.length || state.trajectory[state.trajectory.length - 1].step !== row.step) {
            state.trajectory.push(row);
            if (state.trajectory.length > 300) state.trajectory.shift();
        }
    }
    updateTrajectoryTable();
}

function renderStatusCards() {
    const data = state.vehicle || {};
    const mqtt = data.mqtt || {};
    const cars = data.cars || state.cars || [];
    const onlineCount = cars.filter(car => car.online).length;
    qs("mqttStatusDisplay").textContent = mqtt.connected ? "已连接" : (mqtt.enabled ? "本地通道" : "未启用");
    qs("hilStatusDisplay").textContent = data.running ? "运行中" : statusText(data.status);
    qs("carStatusDisplay").textContent = `${onlineCount}/${cars.length || 0}`;
}

function renderTopics() {
    const mqtt = (state.vehicle && state.vehicle.mqtt) || (state.health && state.health.mqtt) || {};
    const topology = (state.vehicle && state.vehicle.roadTopology) || {};
    const topics = [
        ["Broker", mqtt.brokerUrl || "--", mqtt.connected ? "ok" : "warn"],
        ["Telemetry", mqtt.telemetryTopic || "agilex/odom/#", topology.lastOdometry ? "ok" : "warn"],
        ["Road topology", mqtt.displayTopic || "agilex/road_topology/display/#", topology.messageCount ? "ok" : "warn"],
        ["Goal topic", mqtt.goalTopic || "agilex/road_topology/goal_node", topology.activeGoalNodeId != null ? "ok" : "warn"]
    ];
    qs("topicList").innerHTML = topics.map(([label, value, level]) => `
        <div class="topic-item">
            <span class="topic-dot ${level}"></span>
            <span class="command-main">${label}</span>
            <span class="command-meta">${escapeHtml(String(value))}</span>
        </div>
    `).join("");
}

function renderCommands() {
    const container = qs("commandLog");
    if (!state.commands.length) {
        container.innerHTML = '<p class="hint-text">暂无指令记录</p>';
        return;
    }
    container.innerHTML = state.commands.map(command => `
        <div class="command-item">
            <span class="command-main">${escapeHtml(command.commandType)} -> ${escapeHtml(command.carCode)}</span>
            <span class="command-meta">${escapeHtml(command.status)} ${formatTime(command.requestedAt)}</span>
        </div>
    `).join("");
}

function renderFleet() {
    const tbody = document.getElementById("fleetBody");
    const count = document.getElementById("fleetCount");
    if (!tbody) return;

    const cars = state.cars || [];
    if (count) count.textContent = String(cars.length);
    if (!cars.length) {
        tbody.innerHTML = '<tr class="no-data"><td colspan="7">暂无车辆数据</td></tr>';
        return;
    }

    tbody.innerHTML = cars.map(car => `
        <tr>
            <td>
                <strong>${escapeHtml(car.carName || car.carCode || "--")}</strong><br>
                <span class="route-chip">${escapeHtml(car.carCode || `ID-${car.id}`)}</span>
            </td>
            <td>${escapeHtml(car.carType || "--")}</td>
            <td>${escapeHtml(car.communicationProtocol || "--")}</td>
            <td>${fmt(car.speedMps, 2)} m/s</td>
            <td>${fmt(car.headingDeg, 1)} deg</td>
            <td>${car.latitude && car.longitude ? `${Number(car.latitude).toFixed(6)}, ${Number(car.longitude).toFixed(6)}` : "--"}</td>
            <td>${car.online ? "在线" : "离线"}</td>
        </tr>
    `).join("");
}

function setActiveView(view) {
    if (!view) return;
    document.querySelectorAll("[data-view]").forEach(button => {
        button.classList.toggle("active", button.dataset.view === view);
    });
    document.querySelectorAll(".view-panel").forEach(panel => {
        panel.classList.toggle("active", panel.id === `view-${view}`);
    });
    const title = document.getElementById("viewTitle");
    const titles = {
        overview: "总览地图",
        pointcloud: "经管学院点云底图场景",
        fleet: "小车管理",
        commands: "指令记录"
    };
    if (title) title.textContent = titles[view] || "智控 HIL";
    if (view === "pointcloud") requestAnimationFrame(drawMap);
}

function renderFiles(files) {
    const container = qs("outputFiles");
    if (!files.length) {
        container.innerHTML = '<p class="hint-text">实验结束后将生成 CSV 轨迹和 JSON 摘要文件</p>';
        return;
    }
    container.innerHTML = files.map(file => `
        <div class="file-item">
            <span class="file-name">${escapeHtml(file.name)}</span>
            <span class="file-size">${escapeHtml(file.size || "")}</span>
            <span class="file-time">${escapeHtml(file.mtime || "")}</span>
            <a class="file-link" href="${file.url || `/api/vehicle-control/download/${encodeURIComponent(file.name)}`}" target="_blank">下载</a>
        </div>
    `).join("");
}

function updateTrajectoryTable() {
    const tbody = qs("trajectoryBody");
    const recent = state.trajectory.slice(-24).reverse();
    if (!recent.length) {
        tbody.innerHTML = '<tr class="no-data"><td colspan="7">暂无轨迹数据</td></tr>';
        qs("trajectoryCount").textContent = "共 0 条记录";
        return;
    }
    tbody.innerHTML = recent.map(row => `
        <tr>
            <td>${row.step}</td>
            <td>${row.time}</td>
            <td>${fmt(row.x, 1)}</td>
            <td>${fmt(row.y, 1)}</td>
            <td>${fmt(row.speed, 2)}</td>
            <td>${fmt(row.angle, 1)}</td>
            <td>${escapeHtml(row.edge || "--")}</td>
        </tr>
    `).join("");
    qs("trajectoryCount").textContent = `共 ${state.trajectory.length} 条记录`;
}

function drawMap() {
    const frame = qs("pointcloudFrame");
    const baseImage = qs("pointcloudBaseImage");
    const routeLayer = qs("pointcloudRouteLayer");
    const waypointLayer = qs("waypointLayer");
    const vehicleLayer = qs("vehicleLayer");
    if (!frame || !baseImage || !routeLayer || !waypointLayer || !vehicleLayer) return;

    if (state.pointcloud) {
        frame.style.aspectRatio = `${state.pointcloud.imageWidth} / ${state.pointcloud.imageHeight}`;
        if (baseImage.getAttribute("src") !== state.pointcloud.image) {
            baseImage.src = state.pointcloud.image;
        }
    }

    baseImage.classList.toggle("is-hidden", !state.draw.pointcloud);
    routeLayer.innerHTML = state.draw.route ? renderPointCloudRoutes() : "";
    renderPointCloudWaypoints(waypointLayer);
    renderPointCloudVehicles(vehicleLayer);
}

function renderPointCloudRoutes() {
    const segments = pointCloudRouteSegments();
    const livePath = pointCloudLiveRoutePoints();
    const liveSvg = livePath
        ? `<polyline class="pointcloud-live-route" points="${livePath}" vector-effect="non-scaling-stroke"></polyline>`
        : "";
    const routeSvg = segments.map(segment =>
        `<polyline class="pointcloud-route" points="${segment}" vector-effect="non-scaling-stroke"></polyline>`
    ).join("");
    return liveSvg + routeSvg;
}

function pointCloudRouteSegments() {
    const route = state.navigation;
    if (route && Array.isArray(route.waypoints)) {
        const waypointByIndex = new Map(route.waypoints.map(waypoint => [Number(waypoint.index), waypoint]));
        const topologyEdges = route.topology && Array.isArray(route.topology.undirectedEdges)
            ? route.topology.undirectedEdges
            : [];
        if (topologyEdges.length > 0) {
            return topologyEdges
                .map(edge => {
                    const from = waypointByIndex.get(Number(edge[0]));
                    const to = waypointByIndex.get(Number(edge[1]));
                    return from && to ? pointCloudPolylinePoints([waypointToMapPoint(from), waypointToMapPoint(to)]) : "";
                })
                .filter(Boolean);
        }
        if (route.waypoints.length > 1) {
            return [pointCloudPolylinePoints(route.waypoints.map(waypointToMapPoint))];
        }
    }

    const coords = (state.route && state.route.coordinates) || [];
    return coords.length > 1 ? [pointCloudPolylinePoints(coords)] : [];
}

function pointCloudLiveRoutePoints() {
    const path = state.vehicle && state.vehicle.roadTopology && state.vehicle.roadTopology.lastRoutePath;
    if (!path || !Array.isArray(path.points) || path.points.length < 2) return "";
    return path.points
        .map(point => pointCloudPercent({ lat: Number(point.latitude), lon: Number(point.longitude) }))
        .map(point => `${point.x.toFixed(3)},${point.y.toFixed(3)}`)
        .join(" ");
}

function renderPointCloudWaypoints(container) {
    if (!state.draw.route || !state.navigation || !Array.isArray(state.navigation.waypoints)) {
        container.innerHTML = "";
        return;
    }
    const waypoints = state.navigation.waypoints.filter(waypoint => waypoint.display);
    container.innerHTML = waypoints.map(waypoint => {
        const percent = pointCloudPercent({ lat: waypoint.latitude, lon: waypoint.longitude });
        return `
            <button class="navigation-waypoint-marker" type="button" data-goal-node="${Number(waypoint.index)}"
                style="left:${clamp(percent.x, 0, 100)}%; top:${clamp(percent.y, 0, 100)}%;"
                title="${escapeHtml(waypoint.name || "waypoint")} #${Number(waypoint.index)}">
                <span class="navigation-waypoint-dot">${Number(waypoint.index)}</span>
            </button>
        `;
    }).join("");
    container.querySelectorAll("[data-goal-node]").forEach(button => {
        button.addEventListener("click", event => {
            event.stopPropagation();
            qs("goalNodeInput").value = button.dataset.goalNode;
            sendGoalNode();
        });
    });
}

function renderPointCloudVehicles(container) {
    if (!state.draw.vehicle) {
        container.innerHTML = "";
        return;
    }
    const cars = ((state.vehicle && state.vehicle.cars) || state.cars || [])
        .filter(car => Number.isFinite(Number(car.latitude)) && Number.isFinite(Number(car.longitude)));
    container.innerHTML = cars.map(car => {
        const percent = pointCloudPercent({ lat: Number(car.latitude), lon: Number(car.longitude) });
        const typeClass = car.carType === "REAL" ? "real" : "virtual";
        const onlineClass = car.online ? "online" : "";
        return `
            <span class="vehicle-marker pointcloud-vehicle-marker ${typeClass} ${onlineClass}"
                style="left:${clamp(percent.x, 0, 100)}%; top:${clamp(percent.y, 0, 100)}%; --vehicle-heading:${Number(car.headingDeg || 0)}deg;"
                title="${escapeHtml(car.carCode || "")} · ${Number(car.latitude).toFixed(8)}, ${Number(car.longitude).toFixed(8)}">
                <span class="vehicle-body"></span>
                <span class="vehicle-label">${car.carType === "REAL" ? "真实车" : escapeHtml(car.carCode || "")}</span>
                <span class="vehicle-id">${escapeHtml(car.carCode || `ID ${car.id}`)}</span>
            </span>
        `;
    }).join("");
}

function waypointToMapPoint(waypoint) {
    return {
        lat: Number(waypoint.latitude),
        lon: Number(waypoint.longitude)
    };
}

function pointCloudPolylinePoints(routePoints) {
    return routePoints
        .map(routePoint => {
            const point = pointCloudPercent(routePoint);
            return `${point.x.toFixed(3)},${point.y.toFixed(3)}`;
        })
        .join(" ");
}

function pointCloudPercent(point) {
    const layer = state.pointcloud;
    if (!layer || !layer.bounds) return { x: 50, y: 50 };
    const widthDeg = Math.max(layer.bounds.maxLon - layer.bounds.minLon, Number.EPSILON);
    const heightDeg = Math.max(layer.bounds.maxLat - layer.bounds.minLat, Number.EPSILON);
    return {
        x: ((Number(point.lon) - layer.bounds.minLon) / widthDeg) * 100,
        y: ((layer.bounds.maxLat - Number(point.lat)) / heightDeg) * 100
    };
}

function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
}

function drawBackground(ctx, width, height) {
    ctx.fillStyle = "#101820";
    ctx.fillRect(0, 0, width, height);
    const grad = ctx.createLinearGradient(0, 0, width, height);
    grad.addColorStop(0, "rgba(44,90,160,0.18)");
    grad.addColorStop(1, "rgba(34,160,107,0.12)");
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, width, height);
}

function drawGrid(ctx, width, height) {
    ctx.save();
    ctx.strokeStyle = "rgba(255,255,255,0.08)";
    ctx.lineWidth = Math.max(1, window.devicePixelRatio);
    const gap = 54 * window.devicePixelRatio;
    for (let x = 0; x <= width; x += gap) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, height);
        ctx.stroke();
    }
    for (let y = 0; y <= height; y += gap) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(width, y);
        ctx.stroke();
    }
    ctx.restore();
}

function drawPointcloud(ctx, projection, width, height) {
    const bounds = state.pointcloud.bounds;
    const nw = projection.project(bounds.maxLat, bounds.minLon);
    const se = projection.project(bounds.minLat, bounds.maxLon);
    const x = Math.min(nw.x, se.x);
    const y = Math.min(nw.y, se.y);
    const w = Math.abs(se.x - nw.x);
    const h = Math.abs(se.y - nw.y);
    ctx.save();
    ctx.globalAlpha = 0.82;
    ctx.drawImage(state.pointcloudImage, x, y, w, h);
    ctx.globalAlpha = 1;
    ctx.strokeStyle = "rgba(255,255,255,0.28)";
    ctx.lineWidth = 2 * window.devicePixelRatio;
    ctx.strokeRect(x, y, w, h);
    ctx.restore();
}

function drawRoute(ctx, projection) {
    const coords = (state.route && state.route.coordinates) || [];
    if (coords.length < 2) return;
    ctx.save();
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    ctx.strokeStyle = "rgba(255,255,255,0.85)";
    ctx.lineWidth = 10 * window.devicePixelRatio;
    pathForCoords(ctx, projection, coords);
    ctx.stroke();
    ctx.strokeStyle = "#22A06B";
    ctx.lineWidth = 5 * window.devicePixelRatio;
    pathForCoords(ctx, projection, coords);
    ctx.stroke();
    ctx.restore();
}

function drawWaypoints(ctx, projection) {
    const points = routeWaypoints();
    ctx.save();
    points.forEach((point, index) => {
        const p = projection.project(point.latitude, point.longitude);
        ctx.beginPath();
        ctx.fillStyle = point.display || index === 0 ? "#D39B2A" : "#E7EDF3";
        ctx.strokeStyle = "#1f2937";
        ctx.lineWidth = 2 * window.devicePixelRatio;
        ctx.arc(p.x, p.y, (point.display || index === 0 ? 6 : 4) * window.devicePixelRatio, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
        if (point.display || index === 0) {
            drawLabel(ctx, p.x, p.y - 14 * window.devicePixelRatio, point.name || `WP-${index + 1}`);
        }
    });
    ctx.restore();
}

function drawVehicle(ctx, projection, data) {
    if (typeof data.latitude !== "number" || typeof data.longitude !== "number") return;
    const p = projection.project(data.latitude, data.longitude);
    const angle = ((data.angle || 0) - 90) * Math.PI / 180;
    ctx.save();
    ctx.translate(p.x, p.y);
    ctx.rotate(angle);
    const scale = window.devicePixelRatio;
    ctx.fillStyle = "#2C5AA0";
    ctx.strokeStyle = "#FFFFFF";
    ctx.lineWidth = 2 * scale;
    ctx.beginPath();
    ctx.moveTo(18 * scale, 0);
    ctx.lineTo(-12 * scale, -9 * scale);
    ctx.lineTo(-7 * scale, 0);
    ctx.lineTo(-12 * scale, 9 * scale);
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
    ctx.restore();

    ctx.save();
    ctx.strokeStyle = "rgba(44,90,160,0.35)";
    ctx.lineWidth = 3 * window.devicePixelRatio;
    ctx.beginPath();
    ctx.arc(p.x, p.y, 24 * window.devicePixelRatio, 0, Math.PI * 2);
    ctx.stroke();
    drawLabel(ctx, p.x, p.y + 28 * window.devicePixelRatio, state.activeCar ? state.activeCar.carCode : "CAV");
    ctx.restore();
}

function drawLabel(ctx, x, y, text) {
    const scale = window.devicePixelRatio;
    ctx.save();
    ctx.font = `${12 * scale}px "Microsoft YaHei", Arial`;
    const paddingX = 7 * scale;
    const paddingY = 4 * scale;
    const width = ctx.measureText(text).width + paddingX * 2;
    const height = 22 * scale;
    ctx.fillStyle = "rgba(255,255,255,0.92)";
    roundRect(ctx, x - width / 2, y - height / 2, width, height, 4 * scale);
    ctx.fill();
    ctx.fillStyle = "#2C5AA0";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(text, x, y + paddingY / 2);
    ctx.restore();
}

function pathForCoords(ctx, projection, coords) {
    ctx.beginPath();
    coords.forEach((coord, index) => {
        const p = projection.project(coord.lat, coord.lon);
        if (index === 0) ctx.moveTo(p.x, p.y);
        else ctx.lineTo(p.x, p.y);
    });
}

function makeProjection(width, height) {
    const all = [];
    if (state.pointcloud && state.pointcloud.bounds) {
        const b = state.pointcloud.bounds;
        all.push({ lat: b.minLat, lon: b.minLon }, { lat: b.maxLat, lon: b.maxLon });
    }
    if (state.route && state.route.coordinates) {
        all.push(...state.route.coordinates);
    }
    if (state.vehicle && state.vehicle.latitude && state.vehicle.longitude) {
        all.push({ lat: state.vehicle.latitude, lon: state.vehicle.longitude });
    }
    if (!all.length) {
        all.push({ lat: 38.884, lon: 121.52 }, { lat: 38.885, lon: 121.521 });
    }

    const minLat = Math.min(...all.map(p => p.lat));
    const maxLat = Math.max(...all.map(p => p.lat));
    const minLon = Math.min(...all.map(p => p.lon));
    const maxLon = Math.max(...all.map(p => p.lon));
    const pad = 42 * window.devicePixelRatio;
    const latSpan = Math.max(0.0001, maxLat - minLat);
    const lonSpan = Math.max(0.0001, maxLon - minLon);
    const scale = Math.min((width - pad * 2) / lonSpan, (height - pad * 2) / latSpan);
    const contentW = lonSpan * scale;
    const contentH = latSpan * scale;
    const offsetX = (width - contentW) / 2;
    const offsetY = (height - contentH) / 2;

    return {
        project(lat, lon) {
            return {
                x: offsetX + (lon - minLon) * scale,
                y: offsetY + (maxLat - lat) * scale
            };
        }
    };
}

function routeWaypoints() {
    if (qs("routeSelect").value === "NAVIGATION_WAYPOINTS_LATEST") {
        return (state.navigation && state.navigation.waypoints) || [];
    }
    if (state.route && state.route.snappedWaypoints) {
        return state.route.snappedWaypoints.map((point, index) => ({
            name: point.waypointCode || `WP-${index + 1}`,
            latitude: point.snappedLat,
            longitude: point.snappedLon,
            display: index === 0 || index === state.route.snappedWaypoints.length - 1 || index % 2 === 0
        }));
    }
    return [];
}

function updateSpeedDisplay() {
    const value = Number(qs("targetSpeed").value || 0);
    qs("speedDisplay").textContent = `${value.toFixed(1)} m/s`;
    qs("speedKmh").textContent = `(${(value * 3.6).toFixed(1)} km/h)`;
}

function setStatus(text) {
    qs("statusValue").textContent = text;
}

function setServerStatus(ok, text) {
    const el = qs("serverStatus");
    el.textContent = text;
    el.style.color = ok ? "#22A06B" : "#C83E4D";
}

function markStepDone(id, done = true) {
    qs(id).classList.toggle("step-done", done);
}

function activeCarId() {
    return Number(qs("carSelect").value || (state.activeCar && state.activeCar.id) || 1);
}

function statusText(status) {
    return {
        idle: "就绪",
        running: "运行中",
        stopped: "已停车",
        completed: "已完成"
    }[status] || status || "未知";
}

async function apiGet(path) {
    const response = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`${path} ${response.status}`);
    return response.json();
}

async function apiPost(path, payload) {
    const response = await fetch(`${API_BASE}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload || {})
    });
    if (!response.ok) {
        let message = `${path} ${response.status}`;
        try {
            const body = await response.json();
            message = body.detail || body.message || message;
        } catch {
            /* keep fallback message */
        }
        throw new Error(message);
    }
    return response.json();
}

function qs(id) {
    return document.getElementById(id);
}

function fmt(value, digits) {
    const number = Number(value);
    return Number.isFinite(number) ? number.toFixed(digits) : "--";
}

function formatTime(value) {
    if (!value) return "";
    const text = String(value);
    return text.includes("T") ? text.split("T")[1].slice(0, 8) : text.slice(0, 8);
}

function escapeHtml(value) {
    return String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

function roundRect(ctx, x, y, w, h, r) {
    const radius = Math.min(r, w / 2, h / 2);
    ctx.beginPath();
    ctx.moveTo(x + radius, y);
    ctx.arcTo(x + w, y, x + w, y + h, radius);
    ctx.arcTo(x + w, y + h, x, y + h, radius);
    ctx.arcTo(x, y + h, x, y, radius);
    ctx.arcTo(x, y, x + w, y, radius);
    ctx.closePath();
}
