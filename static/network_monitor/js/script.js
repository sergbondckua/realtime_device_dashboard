// const API_ENDPOINT = '/api/device/zyxel/';
// let currentData = null;
// let updateInterval = null;
// let currentFilter = 'all';
//
// function formatBytes(bytes) {
//     if (bytes === 0) return '0 B';
//     const k = 1024;
//     const sizes = ['B', 'KB', 'MB', 'GB'];
//     let result = [];
//     let remaining = bytes;
//
//     for (let i = sizes.length - 1; i >= 0; i--) {
//         const unit = Math.pow(k, i);
//         if (remaining >= unit) {
//             const value = Math.floor(remaining / unit);
//             result.push(`<span class="bold_text red_text">${value}</span><span class="div_small">${sizes[i]}</span>`);
//             remaining = remaining % unit;
//         }
//     }
//
//     return result.length > 0 ? result.join(' ') : '<span class="bold_text red_text">0</span><span class="div_small">B</span>';
// }
//
// function formatSpeed(bps) {
//     if (bps === 0) return '0bps';
//     const k = 1000; // Для мережевих швидкостей часто використовують 1000, а не 1024
//     const sizes = ['bps', 'Kbps', 'Mbps', 'Gbps'];
//     let i = 0;
//     while (bps >= k && i < sizes.length - 1) {
//         bps /= k;
//         i++;
//     }
//     return `${bps.toFixed(1)}${sizes[i]}`;
// }
//
// function renderSystemInfo(systemInfo) {
//     const container = document.getElementById('systemInfo');
//     container.innerHTML = `
//         <div class="info-item">
//             <div class="info-label">Модель обладнання</div>
//             <div class="info-value">${systemInfo.model || 'Невідомо'}</div>
//         </div>
//         <div class="info-item">
//             <div class="info-label">Системне ім'я</div>
//             <div class="info-value">${systemInfo.system_name || 'Невідомо'}</div>
//         </div>
//         <div class="info-item">
//             <div class="info-label">MAC-адреса</div>
//             <div class="info-value">${systemInfo.mac_address || 'Невідомо'}</div>
//         </div>
//         <div class="info-item">
//             <div class="info-label">Час роботи</div>
//             <div class="info-value">${systemInfo.uptime || 'Невідомо'}</div>
//         </div>
//     `;
// }
//
// function renderPorts(interfaces) {
//     const container = document.getElementById('portsContainer');
//     let html = '';
//
//     const portEntries = Object.entries(interfaces)
//         .sort(([a], [b]) => parseInt(a) - parseInt(b));
//
//     for (const [id, port] of portEntries) {
//         const isConnected = port.connection !== null && port.connection !== undefined && port.connection !== '';
//         const isActive = port.status === 1; // 1 = up, 2 = down (link status)
//         const isUp = port.admin_status === 1; // 1 = enabled, 0 = disabled (admin status)
//         const hasTraffic = (port.in_octets > 0 || port.out_octets > 0) && (port.speed_in > 0 || port.speed_out > 0);
//         const hasErrors = port.in_errors > 0 || port.out_errors > 0;
//
//         html += `
//             <div class="item" data-port="${id}" data-status="${port.status}" data-admin="${port.admin_status}" data-connected="${isConnected}" data-errors="${hasErrors}">
//                 <div class="port_number">
//                     ${id}
//                     <span class="mobile-only mobile-label">Порт</span>
//                     ${isConnected ? '<div class="port_edit">✏️</div>' : ''}
//                 </div>
//
//                 <div class="port_connection">
//                     <span class="mobile-only mobile-label">Комутація</span>
//                     ${!isConnected ?
//             // `<div class="add-connection">➕ Додати підключення</div>
//             `             ${port.alias ? `<span class="label_backblack">${port.alias}</span>` : ''}` :
//             `<div class="client-name">${port.connection}</div>
//                          ${port.address ? `<div class="address">${port.address}</div>` : ''}
//                          ${port.alias ? '<span class="label_backblack">${port.alias}</span>' : ''}
//                          ${port.descr ? `<div class="port-descr"><b>Port descr:</b> ${port.descr}</div>` : ''}`
//         }
//                     <div class="port-descr"><b>Name:</b> ${port.name || 'N/A'}</div>
//                 </div>
//
//                 <div class="port_admin_status ${isUp ? 'port_green' : 'port_red'}">
//                     <span class="mobile-only mobile-label">Адмін статус</span>
//                     ${isUp ? 'активен' : 'вимк'}
//                 </div>
//
//                 <div class="port_link_status ${isActive ? 'port_green' : 'port_red'}">
//                     <span class="mobile-only mobile-label">Лінк</span>
//                     ${isActive ? 'up' : 'down'}
//                     ${isActive && port.speed ? `<br>${formatSpeed(port.speed)}` : ''}
//                 </div>
//
//                 <div class="port_color ${isActive ? 'active' : ''}"></div>
//
//                 <div class="port_traf">
//                     <span class="mobile-only mobile-label">Трафік</span>
//                     in: ${formatBytes(port.in_octets || 0)}<br>
//                     out: ${formatBytes(port.out_octets || 0)}
//                     ${hasTraffic ?
//             `<div class="traf-speed">
//                             <span class="traf-icon us-traf-in">▲</span><b>${formatSpeed(port.speed_in || 0)}</b>
//                             <span class="traf-icon us-traf-out">▼</span><b>${formatSpeed(port.speed_out || 0)}</b>
//                         </div>` : ''
//         }
//                     ${hasErrors ? `<div class="info_block">Помилки: In ${port.in_errors}, Out ${port.out_errors}</div>` : ''}
//                 </div>
//             </div>
//         `;
//     }
//
//     container.innerHTML = html;
// }
//
// function filterPorts(filter, event) {
//     currentFilter = filter;
//
//     // Оновлення активної кнопки
//     document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
//     if (event && event.target) {
//         event.target.classList.add('active');
//     } else { // Для ініціального виклику або після оновлення даних
//         const targetBtn = document.querySelector(`.filter-btn[onclick*="${filter}"]`);
//         if (targetBtn) {
//             targetBtn.classList.add('active');
//         }
//     }
//
//     // Фільтрація портів
//     const ports = document.querySelectorAll('.item[data-port]');
//     ports.forEach(port => {
//         const status = parseInt(port.dataset.status); // Link status (1=up, 2=down)
//         const admin = parseInt(port.dataset.admin); // Admin status (1=enabled, 0=disabled)
//         const connected = port.dataset.connected === 'true';
//         const errors = port.dataset.errors === 'true';
//         let show = false;
//
//         switch (filter) {
//             case 'all':
//                 show = true;
//                 break;
//             case 'active':
//                 show = status === 1; // Link is up
//                 break;
//             case 'inactive':
//                 show = status !== 1; // Link is down
//                 break;
//             case 'connected':
//                 show = connected;
//                 break;
//             case 'errors':
//                 show = errors;
//                 break;
//         }
//
//         port.style.display = show ? 'grid' : 'none';
//     });
// }
//
// function updateLastUpdateTime() {
//     const now = new Date();
//     const timeString = now.toLocaleTimeString('uk-UA');
//     document.getElementById('lastUpdateTime').textContent = timeString;
// }
//
// function updateConnectionStatus(isOnline) {
//     const indicator = document.getElementById('connectionStatus');
//     const text = document.getElementById('connectionText');
//
//     if (isOnline) {
//         indicator.className = 'status-indicator status-online';
//         text.textContent = 'Підключення активне';
//     } else {
//         indicator.className = 'status-indicator status-offline';
//         text.textContent = 'Помилка підключення';
//     }
// }
//
// async function fetchData() {
//     try {
//         const response = await fetch(API_ENDPOINT);
//         if (!response.ok) {
//             throw new Error(`HTTP error! status: ${response.status}`);
//         }
//         const data = await response.json();
//         currentData = data;
//         renderSystemInfo(currentData.system_info);
//         renderPorts(currentData.interfaces);
//         updateLastUpdateTime();
//         updateConnectionStatus(true);
//
//         // Застосовуємо поточний фільтр після завантаження даних
//         filterPorts(currentFilter);
//
//     } catch (error) {
//         console.error('Помилка завантаження даних:', error);
//         updateConnectionStatus(false);
//         // Очищаємо вміст або показуємо повідомлення про помилку, якщо дані не завантажились
//         document.getElementById('systemInfo').innerHTML = `<div class="loading">Не вдалося завантажити системну інформацію.</div>`;
//         document.getElementById('portsContainer').innerHTML = `<div class="loading">Не вдалося завантажити дані портів.</div>`;
//     }
// }

function startAutoUpdate() {
    fetchData(); // Перший запуск одразу
    updateInterval = setInterval(fetchData, 5000); // Оновлення кожні 30 секунд
}

function stopAutoUpdate() {
    if (updateInterval) {
        clearInterval(updateInterval);
        updateInterval = null;
    }
}

// Ініціалізація при завантаженні сторінки
document.addEventListener('DOMContentLoaded', function () {
    startAutoUpdate();
});

// Зупинка оновлень при закритті сторінки (наприклад, при переході на іншу сторінку)
window.addEventListener('beforeunload', function () {
    stopAutoUpdate();
});

// Обробка видимості сторінки: зупиняти оновлення, якщо вкладка неактивна
document.addEventListener('visibilitychange', function () {
    if (document.hidden) {
        stopAutoUpdate();
        document.getElementById('autoUpdateStatus').textContent = 'Призупинено';
    } else {
        startAutoUpdate();
        document.getElementById('autoUpdateStatus').textContent = 'Увімкнено';
    }
});