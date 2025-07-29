const DeviceMonitor = (function() {
    let currentFilter = 'all';
    let refreshInterval;

    function init(deviceIp) {
        startAutoRefresh(deviceIp);
        setupEventListeners();
    }

    function startAutoRefresh(deviceIp) {
        fetchData(deviceIp);
        refreshInterval = setInterval(() => fetchData(deviceIp), 10000);
    }

    function fetchData(deviceIp) {
        document.getElementById('loading').style.display = 'flex';
        fetch(`/api/device/${deviceIp}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error('Network response was not ok');
                }
                return response.json();
            })
            .then(data => {
                document.getElementById('device-details-content').innerHTML = generateDeviceContent(data);
                updateHeaderStatus(data.device_status);
                setupPortFilters();
                filterPorts(currentFilter);
            })
            .catch(error => {
                console.error('Помилка завантаження даних пристрою:', error);
                document.getElementById('device-details-content').innerHTML = `
                <div class="info-card empty-state">
                    <h2><i class="fas fa-triangle-exclamation"></i> Помилка завантаження</h2>
                    <p>Не вдалося отримати дані. Пристрій може бути недоступний.</p>
                </div>`;
                updateHeaderStatus(false);
            })
            .finally(() => {
                document.getElementById('loading').style.display = 'none';
            });
    }

    function updateHeaderStatus(isOnline) {
        const container = document.getElementById('device-status-container');
        const text = document.getElementById('device-status-text');
        const iconClass = isOnline ? 'fa-circle-check' : 'fa-circle-xmark';
        const statusClass = isOnline ? 'online' : 'offline';

        container.className = `status-item`;
        text.textContent = isOnline ? 'ONLINE' : 'OFFLINE';
        container.innerHTML = `
        <span class="status-icon ${statusClass}">
            <i class="fas ${iconClass}"></i>
        </span>
        <span id="device-status-text">${isOnline ? 'ONLINE' : 'OFFLINE'}</span>`;
    }

    function filterPorts(filterType) {
        currentFilter = filterType;
        const allRows = document.querySelectorAll('.interface-row');

        allRows.forEach(row => {
            switch (filterType) {
                case 'all':
                    row.style.display = '';
                    break;
                case 'active':
                    if (row.classList.contains('active-port')) {
                        row.style.display = '';
                    } else {
                        row.style.display = 'none';
                    }
                    break;
                case 'inactive':
                    if (row.classList.contains('inactive-port')) {
                        row.style.display = '';
                    } else {
                        row.style.display = 'none';
                    }
                    break;
            }
        });
    }

    function setupPortFilters() {
        document.querySelectorAll('.filter-btn').forEach(btn => {
            btn.addEventListener('click', function () {
                document.querySelectorAll('.filter-btn').forEach(b => {
                    b.classList.remove('active');
                });
                this.classList.add('active');
                filterPorts(this.dataset.filter);
            });
        });
    }

    function generateDeviceContent(data) {
        if (!data.device_status) {
            return `
        <div class="info-card empty-state">
            <h2><i class="fas fa-triangle-exclamation"></i> Дані недоступні</h2>
            <p>Пристрій офлайн або не вдалося отримати інформацію.</p>
        </div>`;
        }

        let content = '';

        if (data.system_info) {
            const sys = data.system_info;
            content += `
        <div class="info-card">
            <h2><i class="fas fa-chart-bar"></i> Системна інформація</h2>
            <div class="info-grid">
                <div class="info-item"><div class="info-label">Модель</div><div class="info-value">${sys.model || 'N/A'}</div></div>
                <div class="info-item"><div class="info-label">Ім'я</div><div class="info-value">${sys.system_name || 'N/A'}</div></div>
                <div class="info-item"><div class="info-label">MAC</div><div class="info-value">${sys.mac_address || 'N/A'}</div></div>
                <div class="info-item"><div class="info-label">Час роботи</div><div class="info-value">${sys.uptime || 'N/A'}</div></div>
            </div>
        </div>`;
        }

        if (data.interfaces && Object.keys(data.interfaces).length > 0) {
            let interfacesHtml = `
        <div class="port-filter">
            <button class="filter-btn ${currentFilter === 'all' ? 'active' : ''}" data-filter="all">Усі порти</button>
            <button class="filter-btn ${currentFilter === 'active' ? 'active' : ''}" data-filter="active">Активні</button>
            <button class="filter-btn ${currentFilter === 'inactive' ? 'active' : ''}" data-filter="inactive">Неактивні</button>
        </div>
        <div id="interfaces-list">`;

            for (const [id, iface] of Object.entries(data.interfaces)) {
                const isActive = iface.admin_status === 1 && iface.oper_status === 1;
                const portClass = isActive ? 'active-port' : 'inactive-port';
                const portIndex = isActive ?
                    iface.index +
                    '<i class="fas fa-bolt active-icon"></i>' :
                    iface.index;

                const speedMbps = iface.speed ? Math.floor(iface.speed / 1000000) : 0;
                const inMB = ((iface.in_octets || 0) / 1024 / 1024).toFixed(2);
                const outMB = ((iface.out_octets || 0) / 1024 / 1024).toFixed(2);
                const adminUp = iface.admin_status === 1;
                const operUp = iface.oper_status === 1;

                let errorsHtml = '';
                if (iface.in_errors || iface.out_errors) {
                    errorsHtml = `<div class="interface-errors"><i class="fas fa-triangle-exclamation"></i> ${iface.in_errors || 0}/${iface.out_errors || 0}</div>`;
                }

                interfacesHtml += `
            <div class="interface-row ${portClass}">
                <div class="interface-name"><span class="port-index">${portIndex}</span> ${iface.name}</div>
                <div class="interface-details"><span>${iface.alias || ''}</span> <span class="speed"><i class="fas fa-gauge-high"></i> ${speedMbps} Mbps</span></div>
                <div class="interface-status">
                    <span class="status-tag ${adminUp ? 'status-up' : 'status-down'}">Admin: ${adminUp ? 'UP' : 'DOWN'}</span>
                    <span class="status-tag ${operUp ? 'status-up' : 'status-down'}">Port: ${operUp ? 'UP' : 'DOWN'}</span>
                </div>
                <div class="interface-traffic">
                    <div><i class="fas fa-arrow-down"></i> ${inMB} MB</div>
                    <div><i class="fas fa-arrow-up"></i> ${outMB} MB</div>
                </div>
                ${errorsHtml}
            </div>`;
            }
            interfacesHtml += `</div>`;
            content += `<div class="info-card"><h2><i class="fas fa-plug"></i> Інтерфейси</h2>${interfacesHtml}</div>`;
        }

        return content;
    }

    function setupEventListeners() {
        if (document.querySelector('.port-filter')) {
            setupPortFilters();
        }
    }

    return {
        init
    };
})();