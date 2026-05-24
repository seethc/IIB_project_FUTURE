document.addEventListener('DOMContentLoaded', () => {
    const deviceList = document.getElementById('device-list');
    const emptyState = document.getElementById('empty-state');
    const totpView = document.getElementById('totp-view');
    const activeDeviceName = document.getElementById('active-device-name');
    const totpCode = document.getElementById('totp-code');
    const progressCircle = document.getElementById('progress-circle');
    const patientInfoBtn = document.getElementById('patient-info-btn');
    const patientModal = document.getElementById('patient-modal');
    const closePatientModalBtn = document.getElementById('close-patient-modal-btn');
    const patientReadView = document.getElementById('patient-read-view');
    const patientForm = document.getElementById('patient-form');
    const patientEditBtn = document.getElementById('patient-edit-btn');
    const patientCancelBtn = document.getElementById('patient-cancel-btn');
    const patientSaveBtn = document.getElementById('patient-save-btn');
    const patientViewName = document.getElementById('patient-view-name');
    const patientViewAge = document.getElementById('patient-view-age');
    const patientViewPhone = document.getElementById('patient-view-phone');
    const patientViewEmergency = document.getElementById('patient-view-emergency');
    const patientViewAllergies = document.getElementById('patient-view-allergies');
    const patientViewNotes = document.getElementById('patient-view-notes');
    const patientNameInput = document.getElementById('patient-name');
    const patientAgeInput = document.getElementById('patient-age');
    const patientPhoneInput = document.getElementById('patient-phone');
    const patientEmergencyInput = document.getElementById('patient-emergency-contact');
    const patientAllergiesInput = document.getElementById('patient-allergies');
    const patientNotesInput = document.getElementById('patient-notes');

    const developerModeBtn = document.getElementById('developer-mode-btn');
    const userModeBtn = document.getElementById('user-mode-btn');
    const addDeviceBtn = document.getElementById('add-device-btn');
    const editDeviceBtn = document.getElementById('edit-device-btn');
    const deleteDeviceBtn = document.getElementById('delete-device-btn');
    const registerModal = document.getElementById('register-modal');
    const closeModalBtn = document.querySelector('.close-modal');
    const registerForm = document.getElementById('register-form');
    const deviceNameInput = document.getElementById('device-name');

    const statusKey = document.getElementById('status-key');
    const statusElapsed = document.getElementById('status-elapsed');
    const statusTimestep = document.getElementById('status-timestep');
    const resetKeyBtn = document.getElementById('reset-key-btn');

    const adapterPortSelect = document.getElementById('adapter-port');
    const tokenPortSelect = document.getElementById('token-port');
    const tokenPortLabel = document.getElementById('token-port-label');
    const uploadPortSelect = document.getElementById('upload-port');
    const firmwareTarget = document.getElementById('firmware-target');
    const timestepSelect = document.getElementById('timestep-select');
    const refreshHardwareBtn = document.getElementById('refresh-hardware-btn');
    const modeUpdiBtn = document.getElementById('mode-updi-btn');
    const modeUartBtn = document.getElementById('mode-uart-btn');
    const modeStatus = document.getElementById('mode-status');
    const flashFirmwareBtn = document.getElementById('flash-firmware-btn');
    const flashStatus = document.getElementById('flash-status');
    const tokenHelloBtn = document.getElementById('token-hello-btn');
    const tokenReadSerialBtn = document.getElementById('token-read-serial-btn');
    const provisionKeyBtn = document.getElementById('provision-key-btn');
    const pendantResetStatus = document.getElementById('pendant-reset-status');
    const clearLogBtn = document.getElementById('clear-log-btn');
    const hardwareLog = document.getElementById('hardware-log');

    let devices = [];
    let activeDeviceId = null;
    let totpInterval = null;
    let activeTimestep = 30;
    let flashPollInterval = null;
    let selectedMode = null;
    let hardwareMock = false;
    let interfaceMode = localStorage.getItem('interfaceMode') || 'developer';
    let progressState = null;
    let secretRevealBusy = false;
    let secretRevealTimeout = null;
    let identifyBusy = false;
    let uartBusy = false;
    let identifyInterval = null;
    let connectedDeviceId = null;
    let detectedToken = null;
    const CIRCUMFERENCE = 2 * Math.PI * 45;

    progressCircle.style.strokeDasharray = CIRCUMFERENCE;
    progressCircle.style.strokeDashoffset = CIRCUMFERENCE;

    function appendHardwareLog(message) {
        const timestamp = new Date().toLocaleTimeString();
        hardwareLog.textContent += `[${timestamp}] ${message}\n`;
        hardwareLog.scrollTop = hardwareLog.scrollHeight;
    }

    function showUserDialog(message, options = {}) {
        const {
            title = 'Notice',
            confirmText = 'OK',
            cancelText = '',
            danger = false
        } = options;

        if (interfaceMode !== 'user') {
            if (cancelText) {
                return Promise.resolve(window.confirm(message));
            }
            window.alert(message);
            return Promise.resolve(true);
        }

        return new Promise((resolve) => {
            const overlay = document.createElement('div');
            overlay.className = 'modal app-dialog';

            const content = document.createElement('div');
            content.className = 'modal-content glass-panel';

            const header = document.createElement('div');
            header.className = 'modal-header';
            const heading = document.createElement('h3');
            heading.textContent = title;
            header.appendChild(heading);

            const body = document.createElement('div');
            body.className = 'modal-body';
            const description = document.createElement('p');
            description.className = 'modal-desc';
            description.textContent = message;
            body.appendChild(description);

            const actions = document.createElement('div');
            actions.className = 'dialog-actions';

            function finish(value) {
                overlay.remove();
                resolve(value);
            }

            if (cancelText) {
                const cancelButton = document.createElement('button');
                cancelButton.type = 'button';
                cancelButton.className = 'secondary-btn';
                cancelButton.textContent = cancelText;
                cancelButton.addEventListener('click', () => finish(false));
                actions.appendChild(cancelButton);
            }

            const confirmButton = document.createElement('button');
            confirmButton.type = 'button';
            confirmButton.className = danger ? 'secondary-btn danger-border' : 'primary-btn';
            confirmButton.textContent = confirmText;
            confirmButton.addEventListener('click', () => finish(true));
            actions.appendChild(confirmButton);

            overlay.addEventListener('click', (event) => {
                if (event.target === overlay) finish(false);
            });

            content.appendChild(header);
            content.appendChild(body);
            content.appendChild(actions);
            overlay.appendChild(content);
            document.body.appendChild(overlay);
            confirmButton.focus();
        });
    }

    function notifyUser(message, title = 'Notice') {
        return showUserDialog(message, { title, confirmText: 'OK' });
    }

    function confirmUser(message, title = 'Confirm', danger = false, confirmText = null) {
        return showUserDialog(message, {
            title,
            confirmText: confirmText || (danger ? 'Reset' : 'Continue'),
            cancelText: 'Cancel',
            danger
        });
    }

    function chooseDeveloperDeleteScope(deviceName) {
        return new Promise((resolve) => {
            const overlay = document.createElement('div');
            overlay.className = 'modal app-dialog';

            const content = document.createElement('div');
            content.className = 'modal-content glass-panel';

            const header = document.createElement('div');
            header.className = 'modal-header';
            const heading = document.createElement('h3');
            heading.textContent = 'Delete Pendant';
            header.appendChild(heading);

            const body = document.createElement('div');
            body.className = 'modal-body';
            const description = document.createElement('p');
            description.className = 'modal-desc';
            description.textContent = `${deviceName} is currently plugged in and selected. Choose whether to delete only the backend record or also reset the selected profile on the pendant.`;
            body.appendChild(description);

            const actions = document.createElement('div');
            actions.className = 'dialog-actions stacked-actions';

            function finish(value) {
                overlay.remove();
                resolve(value);
            }

            const localButton = document.createElement('button');
            localButton.type = 'button';
            localButton.className = 'secondary-btn';
            localButton.textContent = 'Backend Only';
            localButton.addEventListener('click', () => finish('local'));

            const bothButton = document.createElement('button');
            bothButton.type = 'button';
            bothButton.className = 'secondary-btn danger-border';
            bothButton.textContent = 'Backend + Pendant';
            bothButton.addEventListener('click', () => finish('hardware'));

            const cancelButton = document.createElement('button');
            cancelButton.type = 'button';
            cancelButton.className = 'secondary-btn';
            cancelButton.textContent = 'Cancel';
            cancelButton.addEventListener('click', () => finish(null));

            overlay.addEventListener('click', (event) => {
                if (event.target === overlay) finish(null);
            });

            actions.appendChild(localButton);
            actions.appendChild(bothButton);
            actions.appendChild(cancelButton);
            content.appendChild(header);
            content.appendChild(body);
            content.appendChild(actions);
            overlay.appendChild(content);
            document.body.appendChild(overlay);
            localButton.focus();
        });
    }

    function confirmDeveloperBackendOnlyDelete(deviceName) {
        return new Promise((resolve) => {
            const overlay = document.createElement('div');
            overlay.className = 'modal app-dialog';

            const content = document.createElement('div');
            content.className = 'modal-content glass-panel';

            const header = document.createElement('div');
            header.className = 'modal-header';
            const heading = document.createElement('h3');
            heading.textContent = 'Delete Backend Record';
            header.appendChild(heading);

            const body = document.createElement('div');
            body.className = 'modal-body';
            const description = document.createElement('p');
            description.className = 'modal-desc';
            description.textContent = `${deviceName} is not the connected selected profile. This will delete only the backend record and the physical pendant will not be changed.`;
            body.appendChild(description);

            const actions = document.createElement('div');
            actions.className = 'dialog-actions';

            function finish(value) {
                overlay.remove();
                resolve(value);
            }

            const cancelButton = document.createElement('button');
            cancelButton.type = 'button';
            cancelButton.className = 'secondary-btn';
            cancelButton.textContent = 'Cancel';
            cancelButton.addEventListener('click', () => finish(false));

            const deleteButton = document.createElement('button');
            deleteButton.type = 'button';
            deleteButton.className = 'secondary-btn danger-border';
            deleteButton.textContent = 'Delete Backend Only';
            deleteButton.addEventListener('click', () => finish(true));

            overlay.addEventListener('click', (event) => {
                if (event.target === overlay) finish(false);
            });

            actions.appendChild(cancelButton);
            actions.appendChild(deleteButton);
            content.appendChild(header);
            content.appendChild(body);
            content.appendChild(actions);
            overlay.appendChild(content);
            document.body.appendChild(overlay);
            deleteButton.focus();
        });
    }

    function confirmUnknownProfileReset() {
        return new Promise((resolve) => {
            const overlay = document.createElement('div');
            overlay.className = 'modal app-dialog';

            const content = document.createElement('div');
            content.className = 'modal-content glass-panel';

            const header = document.createElement('div');
            header.className = 'modal-header';
            const heading = document.createElement('h3');
            heading.textContent = 'Reset Unknown Profile';
            header.appendChild(heading);

            const body = document.createElement('div');
            body.className = 'modal-body';
            const description = document.createElement('p');
            description.className = 'modal-desc';
            description.textContent = 'This profile is registered somewhere else. Developer mode can reset the selected profile on the pendant back to unregistered, with no code.';
            body.appendChild(description);

            const actions = document.createElement('div');
            actions.className = 'dialog-actions';

            function finish(value) {
                overlay.remove();
                resolve(value);
            }

            const cancelButton = document.createElement('button');
            cancelButton.type = 'button';
            cancelButton.className = 'secondary-btn';
            cancelButton.textContent = 'Cancel';
            cancelButton.addEventListener('click', () => finish(false));

            const resetButton = document.createElement('button');
            resetButton.type = 'button';
            resetButton.className = 'secondary-btn danger-border';
            resetButton.textContent = 'Reset Profile';
            resetButton.addEventListener('click', () => finish(true));

            overlay.addEventListener('click', (event) => {
                if (event.target === overlay) finish(false);
            });

            actions.appendChild(cancelButton);
            actions.appendChild(resetButton);
            content.appendChild(header);
            content.appendChild(body);
            content.appendChild(actions);
            overlay.appendChild(content);
            document.body.appendChild(overlay);
            resetButton.focus();
        });
    }

    function promptForPendantName(currentName) {
        return new Promise((resolve) => {
            const overlay = document.createElement('div');
            overlay.className = 'modal app-dialog';

            const content = document.createElement('div');
            content.className = 'modal-content glass-panel';

            const header = document.createElement('div');
            header.className = 'modal-header';
            const heading = document.createElement('h3');
            heading.textContent = 'Rename Pendant';
            header.appendChild(heading);

            const body = document.createElement('div');
            body.className = 'modal-body';

            const group = document.createElement('div');
            group.className = 'input-group';
            const label = document.createElement('label');
            label.textContent = 'Pendant Name';
            const input = document.createElement('input');
            input.type = 'text';
            input.maxLength = 80;
            input.required = true;
            input.autocomplete = 'off';
            input.value = currentName || '';
            group.appendChild(label);
            group.appendChild(input);
            body.appendChild(group);

            const actions = document.createElement('div');
            actions.className = 'dialog-actions';

            function finish(value) {
                overlay.remove();
                resolve(value);
            }

            const cancelButton = document.createElement('button');
            cancelButton.type = 'button';
            cancelButton.className = 'secondary-btn';
            cancelButton.textContent = 'Cancel';
            cancelButton.addEventListener('click', () => finish(null));

            const saveButton = document.createElement('button');
            saveButton.type = 'button';
            saveButton.className = 'primary-btn';
            saveButton.textContent = 'Save';
            saveButton.addEventListener('click', () => {
                const name = input.value.trim();
                if (!name) {
                    input.focus();
                    return;
                }
                finish(name);
            });

            input.addEventListener('keydown', (event) => {
                if (event.key === 'Enter') {
                    event.preventDefault();
                    saveButton.click();
                } else if (event.key === 'Escape') {
                    event.preventDefault();
                    finish(null);
                }
            });

            overlay.addEventListener('click', (event) => {
                if (event.target === overlay) finish(null);
            });

            actions.appendChild(cancelButton);
            actions.appendChild(saveButton);
            content.appendChild(header);
            content.appendChild(body);
            content.appendChild(actions);
            overlay.appendChild(content);
            document.body.appendChild(overlay);
            input.focus();
            input.select();
        });
    }

    function updateEditAvailability() {
        if (!editDeviceBtn) return;
        editDeviceBtn.disabled = !activeDeviceId;
        editDeviceBtn.title = activeDeviceId
            ? 'Rename Pendant'
            : 'Select a pendant before renaming it';
    }

    function updateDeleteAvailability() {
        if (!deleteDeviceBtn) return;
        const canDelete = Boolean(activeDeviceId)
            ? (isDeveloperMode() || activeDeviceId === connectedDeviceId)
            : canDeveloperUnregisterUnknown();
        deleteDeviceBtn.disabled = !canDelete;
        if (!activeDeviceId) {
            deleteDeviceBtn.title = canDeveloperUnregisterUnknown()
                ? 'Reset the unknown registered pendant profile on the device'
                : 'Select a pendant before deleting it';
        } else if (isDeveloperMode()) {
            deleteDeviceBtn.title = activeDeviceId === connectedDeviceId
                ? 'Delete backend record or reset both backend and device'
                : 'Delete backend record only';
        } else {
            deleteDeviceBtn.title = canDelete
                ? 'Delete Pendant'
                : 'Plug in and identify this exact pendant before deleting it';
        }
    }

    function updatePatientInfoAvailability() {
        if (!patientInfoBtn) return;
        patientInfoBtn.disabled = !activeDeviceId;
        patientInfoBtn.title = activeDeviceId
            ? 'Open patient information for this pendant'
            : 'Select a pendant to view patient information';
    }

    function updateHeaderActions() {
        updateEditAvailability();
        updateDeleteAvailability();
        updatePatientInfoAvailability();
    }

    function setFlashStatus(status, isError) {
        flashStatus.textContent = status;
        flashStatus.classList.toggle('error', Boolean(isError));
        flashStatus.classList.toggle('success', status.toLowerCase().includes('succeeded'));
        flashStatus.classList.remove('running');
    }

    function setPendantResetStatus(status, state = 'idle') {
        if (!pendantResetStatus) return;
        pendantResetStatus.textContent = status;
        pendantResetStatus.classList.toggle('running', state === 'running');
        pendantResetStatus.classList.toggle('success', state === 'success');
        pendantResetStatus.classList.toggle('error', state === 'error');
    }

    function setInterfaceMode(mode) {
        interfaceMode = mode === 'user' ? 'user' : 'developer';
        document.body.classList.toggle('user-mode', interfaceMode === 'user');
        document.body.classList.toggle('developer-mode', interfaceMode === 'developer');
        developerModeBtn.classList.toggle('active', interfaceMode === 'developer');
        userModeBtn.classList.toggle('active', interfaceMode === 'user');
        tokenPortLabel.textContent = interfaceMode === 'user' ? 'Serial Port' : 'Pendant UART Port';
        localStorage.setItem('interfaceMode', interfaceMode);
        renderDeviceList();
        updateHeaderActions();

        if (interfaceMode === 'user') {
            syncControlPortToTokenPort();
            appendHardwareLog('User mode: one serial port, fixed 30s step, and Reset Pendant only.');
        } else {
            appendHardwareLog('Developer mode: UPDI flashing and UART diagnostics visible for pendant development.');
        }
    }

    function updateModeUi(mode, pending) {
        selectedMode = mode || null;
        modeUpdiBtn.classList.toggle('selected', selectedMode === 'UPDI');
        modeUartBtn.classList.toggle('selected', selectedMode === 'UART');
        modeUpdiBtn.classList.toggle('pending', pending && mode === 'UPDI');
        modeUartBtn.classList.toggle('pending', pending && mode === 'UART');
        if (pending && selectedMode) {
            modeStatus.textContent = `Switching to ${selectedMode}...`;
            return;
        }
        if (!selectedMode) {
            modeStatus.textContent = 'Mode not selected';
            return;
        }
        modeStatus.textContent = `Confirmed: ${selectedMode}`;
    }

    function isUnconfirmedModeReply(reply) {
        return reply.includes('serial echo only') ||
            reply.includes('no adapter acknowledgement') ||
            reply.startsWith('SENT MODE');
    }

    function selectedValue(select) {
        return select.value || '';
    }

    function selectedTimestep() {
        return interfaceMode === 'user' ? 30 : Number(timestepSelect.value || 30);
    }

    function selectedControlPort() {
        return interfaceMode === 'user'
            ? selectedValue(tokenPortSelect)
            : selectedValue(adapterPortSelect);
    }

    function syncControlPortToTokenPort() {
        if (adapterPortSelect && tokenPortSelect && selectedValue(tokenPortSelect)) {
            adapterPortSelect.value = selectedValue(tokenPortSelect);
        }
    }

    function hardwarePayload() {
        return {
            uart_port: selectedValue(tokenPortSelect),
            token_port: selectedValue(tokenPortSelect),
            timestep: selectedTimestep()
        };
    }

    async function parseJsonResponse(response) {
        const text = await response.text();
        try {
            return text ? JSON.parse(text) : {};
        } catch (error) {
            const preview = text.replace(/\s+/g, ' ').slice(0, 180);
            throw new Error(`Server returned ${response.status} ${response.statusText}: ${preview}`);
        }
    }

    async function postJson(url, payload) {
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload || {})
        });
        const data = await parseJsonResponse(response);
        if (!response.ok || data.success === false) {
            throw new Error(data.error || response.statusText);
        }
        return data;
    }

    function setButtonBusy(button, busy, text) {
        if (!button) return;
        if (busy) {
            button.dataset.originalText = button.innerHTML;
            button.innerHTML = text;
            button.disabled = true;
            return;
        }
        button.innerHTML = button.dataset.originalText || button.innerHTML;
        button.disabled = false;
    }

    function isDeveloperMode() {
        return interfaceMode === 'developer';
    }

    function isUnavailableDetectedToken() {
        return Boolean(detectedToken && !detectedToken.matched && detectedToken.provisioned);
    }

    function canDeveloperUnregisterUnknown() {
        return isDeveloperMode() && isUnavailableDetectedToken();
    }

    function maskKey(secret) {
        return '*'.repeat(Math.max(10, String(secret || '').length));
    }

    function updateStatusKeyDisplay(secret) {
        if (!statusKey) return;
        statusKey.dataset.secret = String(secret || '');
        if (isDeveloperMode()) {
            statusKey.textContent = maskKey(secret);
            statusKey.title = 'Click to verify UART and reveal';
            statusKey.classList.remove('revealed', 'checking');
        } else {
            statusKey.textContent = '****************************************';
            statusKey.title = 'Key hidden in user mode';
            statusKey.classList.remove('revealed', 'checking');
        }
    }

    function populatePortSelect(select, ports, preferred) {
        const current = select.value || preferred || '';
        select.innerHTML = '';

        const seen = new Set();
        ports.forEach((port) => {
            seen.add(port.device);
            const option = document.createElement('option');
            option.value = port.device;
            option.textContent = `${port.device} - ${port.description || 'Serial port'}`;
            select.appendChild(option);
        });

        if (current && !seen.has(current)) {
            const option = document.createElement('option');
            option.value = current;
            option.textContent = current;
            select.appendChild(option);
        }

        if (!select.options.length) {
            const option = document.createElement('option');
            option.value = '';
            option.textContent = 'No serial ports found';
            select.appendChild(option);
        }

        select.value = current || select.options[0].value;
    }

    function populateFirmwareTarget(envs) {
        const current = firmwareTarget.value || '';
        firmwareTarget.innerHTML = '';

        const targets = envs || [];
        targets.forEach((env) => {
            const option = document.createElement('option');
            option.value = env.name;
            option.textContent = env.label || env.name;
            option.title = env.description || env.source || '';
            if (env.recommended) option.selected = true;
            firmwareTarget.appendChild(option);
        });

        if (!firmwareTarget.options.length) {
            const option = document.createElement('option');
            option.value = 'main2';
            option.textContent = 'main2.cpp - Pendant';
            firmwareTarget.appendChild(option);
        }

        if (current && Array.from(firmwareTarget.options).some((option) => option.value === current)) {
            firmwareTarget.value = current;
        }
    }

    async function fetchHardware() {
        try {
            const [portsResponse, envResponse] = await Promise.all([
                fetch('/api/hardware/ports'),
                fetch('/api/hardware/firmware-envs')
            ]);
            const portData = await parseJsonResponse(portsResponse);
            const envData = await parseJsonResponse(envResponse);
            if (!portsResponse.ok) throw new Error(portData.error || portsResponse.statusText);
            if (!envResponse.ok) throw new Error(envData.error || envResponse.statusText);
            const defaults = portData.defaults || {};

            populatePortSelect(adapterPortSelect, portData.ports || [], defaults.adapter_port);
            populatePortSelect(tokenPortSelect, portData.ports || [], defaults.token_port);
            populatePortSelect(uploadPortSelect, portData.ports || [], defaults.upload_port);
            populateFirmwareTarget(envData.envs || []);
            if (interfaceMode === 'user') {
                syncControlPortToTokenPort();
            }

            hardwareMock = Boolean(defaults.mock);
            timestepSelect.value = String(defaults.timestep || 30);
            flashFirmwareBtn.disabled = hardwareMock;
            flashFirmwareBtn.title = hardwareMock
                ? 'Mock mode is enabled; restart the backend without HARDWARE_MOCK to flash.'
                : '';

            if (hardwareMock) {
                setFlashStatus('Mock mode - flashing disabled', true);
                appendHardwareLog('Hardware ready (mock mode). Real UPDI flashing is disabled.');
                appendHardwareLog('Restart the backend without HARDWARE_MOCK=1 before flashing a physical token.');
            } else {
                setFlashStatus('Idle');
                appendHardwareLog('Hardware ready.');
            }

            identifyConnectedToken({ silent: true, autoSelect: true });
        } catch (error) {
            appendHardwareLog(`Hardware discovery failed: ${error.message}`);
        }
    }

    async function setAdapterMode(mode) {
        const upperMode = mode.toUpperCase();
        try {
            updateModeUi(upperMode, true);
            appendHardwareLog(`Switching adapter to ${upperMode}...`);
            const data = await postJson('/api/adapter/mode', {
                port: selectedControlPort(),
                mode
            });
            const reply = data.reply || `OK MODE ${upperMode}`;
            const unconfirmed = isUnconfirmedModeReply(reply);
            updateModeUi(unconfirmed ? null : upperMode, false);
            appendHardwareLog(reply);
            if (unconfirmed) {
                appendHardwareLog(`Adapter did not confirm ${upperMode}; mode not selected.`);
                await notifyUser(`Adapter did not confirm ${upperMode}. Token UART buttons will still test the ATtiny connection directly.`, 'Adapter Mode');
                return false;
            }
            return true;
        } catch (error) {
            updateModeUi(null, false);
            appendHardwareLog(`Adapter mode failed: ${error.message}`);
            await notifyUser(error.message, 'Adapter Mode Failed');
            return false;
        }
    }

    async function ensureUartMode({ silent = false } = {}) {
        syncControlPortToTokenPort();
        if (selectedMode === 'UART') {
            return true;
        }

        if (!silent) {
            appendHardwareLog('Testing ATtiny UART connection directly; backend will try RTS low and RTS high.');
        }
        return true;
    }

    async function startFlash() {
        if (hardwareMock) {
            const message = 'Mock mode is enabled, so the backend will not flash physical hardware. Restart the backend without HARDWARE_MOCK=1.';
            appendHardwareLog(message);
            setFlashStatus('Mock mode - flashing disabled', true);
            await notifyUser(message, 'Flashing Disabled');
            return;
        }

        if (uartBusy) {
            const message = 'Serial port is busy. Wait for the current UART action to finish, then try flashing again.';
            appendHardwareLog(message);
            await notifyUser(message, 'Serial Port Busy');
            return;
        }

        try {
            uartBusy = true;
            setButtonBusy(flashFirmwareBtn, true, 'Flashing...');
            setFlashStatus('Starting...');
            flashStatus.classList.add('running');
            const selectedFirmware = firmwareTarget.selectedOptions[0]?.textContent || selectedValue(firmwareTarget);
            appendHardwareLog(`Starting firmware flash job: ${selectedFirmware}`);
            const data = await postJson('/api/flash', {
                target: selectedValue(firmwareTarget),
                upload_port: selectedValue(uploadPortSelect),
                adapter_port: selectedValue(uploadPortSelect),
                switch_mode: true
            });
            setFlashStatus(`Running job ${data.job.id}`);
            flashStatus.classList.add('running');
            pollFlashJob(data.job.id);
        } catch (error) {
            uartBusy = false;
            appendHardwareLog(`Flash failed to start: ${error.message}`);
            setFlashStatus('Failed to start', true);
            await notifyUser(error.message, 'Flash Failed');
            setButtonBusy(flashFirmwareBtn, false);
        }
    }

    function pollFlashJob(jobId) {
        if (flashPollInterval) clearInterval(flashPollInterval);
        let printed = 0;

        flashPollInterval = setInterval(async () => {
            try {
                const response = await fetch(`/api/jobs/${jobId}`);
                const data = await parseJsonResponse(response);
                if (!response.ok) {
                    throw new Error(data.error || response.statusText);
                }
                const job = data.job;
                const logs = job.logs || [];

                logs.slice(printed).forEach((line) => appendHardwareLog(line));
                printed = logs.length;

                if (job.status === 'succeeded' || job.status === 'failed') {
                    clearInterval(flashPollInterval);
                    flashPollInterval = null;
                    uartBusy = false;
                    appendHardwareLog(`Flash job ${job.status}.`);
                    setFlashStatus(`Flash ${job.status}`, job.status === 'failed');
                    setButtonBusy(flashFirmwareBtn, false);
                }
            } catch (error) {
                clearInterval(flashPollInterval);
                flashPollInterval = null;
                uartBusy = false;
                appendHardwareLog(`Flash polling failed: ${error.message}`);
                setFlashStatus('Flash status lost', true);
                setButtonBusy(flashFirmwareBtn, false);
            }
        }, 1000);
    }

    async function tokenCommand(path, label) {
        if (uartBusy) {
            await notifyUser('Serial port is busy. Wait a moment and try again.', 'Serial Port Busy');
            return null;
        }

        uartBusy = true;
        try {
            if (!(await ensureUartMode())) return null;
            appendHardwareLog(`${label}...`);
            const data = await postJson(path, hardwarePayload());
            const status = data.status;
            appendHardwareLog(data.reply || (status && status.raw) || `${label} OK`);
            if (status && Number.isFinite(status.elapsed)) {
                appendHardwareLog(`ATtiny elapsed count: ${status.elapsed}s, step: ${status.step}s, provisioned: ${status.provisioned ? 'yes' : 'no'}`);
            }
            return data;
        } catch (error) {
            appendHardwareLog(`${label} failed: ${error.message}`);
            await notifyUser(error.message, `${label} Failed`);
            return null;
        } finally {
            uartBusy = false;
        }
    }

    async function identifyConnectedToken({ silent = false, autoSelect = true, force = false } = {}) {
        if (identifyBusy || (!force && uartBusy) || !selectedValue(tokenPortSelect)) return null;

        identifyBusy = true;
        try {
            if (!(await ensureUartMode({ silent }))) return null;
            if (!silent) appendHardwareLog('Identifying connected pendant...');

            const data = await postJson('/api/token/identify', hardwarePayload());
            detectedToken = {
                state: data.state,
                matched: Boolean(data.matched),
                provisioned: Boolean(data.provisioned),
                device: data.device || null
            };
            connectedDeviceId = data.matched && data.device ? data.device.id : null;

            if (data.matched && data.device) {
                if (!silent) appendHardwareLog(`Connected pendant matched: ${data.device.name}`);
                if (autoSelect && activeDeviceId !== data.device.id) {
                    selectDevice(data.device.id);
                } else {
                    renderDeviceList();
                    updateHeaderActions();
                }
            } else {
                if (activeDeviceId) {
                    activeDeviceId = null;
                    showEmptyState();
                }
                renderDeviceList();
                if (!silent) {
                    appendHardwareLog(
                        data.provisioned
                            ? 'Connected pendant is provisioned but is not in this token list.'
                            : 'Connected pendant is unregistered.'
                    );
                }
            }
            updateHeaderActions();

            return data;
        } catch (error) {
            connectedDeviceId = null;
            detectedToken = null;
            renderDeviceList();
            updateHeaderActions();
            if (!silent) appendHardwareLog(`Pendant identification failed: ${error.message}`);
            return null;
        } finally {
            identifyBusy = false;
        }
    }

    function hideStatusKey() {
        if (!statusKey) return;
        statusKey.classList.remove('revealed', 'checking');
        if (isDeveloperMode()) {
            statusKey.title = 'Click to verify UART and reveal';
            statusKey.textContent = maskKey(statusKey.dataset.secret);
        } else {
            statusKey.title = 'Key hidden in user mode';
            statusKey.textContent = '****************************************';
        }
        if (secretRevealTimeout) {
            clearTimeout(secretRevealTimeout);
            secretRevealTimeout = null;
        }
    }

    async function revealStatusKeyWithUart() {
        if (!activeDeviceId || secretRevealBusy || !statusKey) return;
        if (!isDeveloperMode()) {
            return;
        }

        if (statusKey.classList.contains('revealed')) {
            hideStatusKey();
            return;
        }

        if (uartBusy) {
            await notifyUser('Serial port is busy. Wait a moment and try again.', 'Serial Port Busy');
            return;
        }

        uartBusy = true;
        try {
            if (!(await ensureUartMode())) return;
            secretRevealBusy = true;
            statusKey.classList.add('checking');
            statusKey.title = 'Checking UART connection...';
            appendHardwareLog('Checking UART before revealing key...');

            if (activeDeviceId !== connectedDeviceId) {
                await identifyConnectedToken({ silent: true, autoSelect: false, force: true });
            }
            if (activeDeviceId !== connectedDeviceId) {
                throw new Error('The plugged-in pendant does not match this saved token.');
            }

            const data = await postJson(`/api/devices/${activeDeviceId}/verify`, hardwarePayload());
            const status = data.status;
            if (!data.verified || !status) {
                throw new Error(data.error || 'UART verification failed.');
            }
            statusKey.classList.add('revealed');
            statusKey.classList.remove('checking');
            statusKey.title = 'Click to hide';
            statusKey.textContent = devices.find((item) => item.id === activeDeviceId)?.secret_key || statusKey.textContent;
            appendHardwareLog(`UART verified. Key revealed for 20 seconds. ATtiny elapsed: ${status.elapsed}s.`);
            secretRevealTimeout = setTimeout(hideStatusKey, 20000);
        } catch (error) {
            hideStatusKey();
            appendHardwareLog(`Key reveal blocked: ${error.message}`);
            await notifyUser(error.message, 'Key Reveal Blocked');
        } finally {
            uartBusy = false;
            secretRevealBusy = false;
            statusKey.classList.remove('checking');
        }
    }

    async function readRtc() {
        if (uartBusy) {
            await notifyUser('Serial port is busy. Wait a moment and try again.', 'Serial Port Busy');
            return;
        }

        uartBusy = true;
        try {
            if (!(await ensureUartMode())) return;
            appendHardwareLog('READ RTC...');
            const data = await postJson('/api/token/read-rtc', hardwarePayload());
            const rtc = data.rtc;
            appendHardwareLog(rtc.reply || 'OK RTC');
            if (rtc && Number.isFinite(rtc.raw_seconds)) {
                appendHardwareLog(
                    `RTC raw: ${rtc.raw_seconds}s, elapsed: ${rtc.elapsed}s, counter: ${rtc.counter}, overflow seconds: ${rtc.overflow_seconds}, clock: ${rtc.clock}`
                );
            }
        } catch (error) {
            appendHardwareLog(`Read RTC failed: ${error.message}`);
            await notifyUser(error.message, 'Read RTC Failed');
        } finally {
            uartBusy = false;
        }
    }

    async function provisionNewKey() {
        if (activeDeviceId) {
            if (await confirmUser('Reset this pendant with a new random key and reset its timer?', 'Reset Pendant', true)) {
                await resetDevice('reset_pendant');
            }
            return;
        }
        if (isUnavailableDetectedToken() && !isDeveloperMode()) {
            await notifyUser('This pendant profile is already registered elsewhere, so user mode cannot reset it.', 'Reset Blocked');
            return;
        }
        openModal();
    }

    async function fetchDevices() {
        try {
            const response = await fetch('/api/devices');
            const data = await parseJsonResponse(response);
            if (!response.ok) throw new Error(data.error || response.statusText);
            devices = data.devices;
            renderDeviceList();
            if (
                connectedDeviceId &&
                activeDeviceId !== connectedDeviceId &&
                devices.some((device) => device.id === connectedDeviceId)
            ) {
                selectDevice(connectedDeviceId);
            }
        } catch (error) {
            console.error('Failed to fetch devices:', error);
            appendHardwareLog(`Device list failed: ${error.message}`);
        }
    }

    async function registerDevice(name) {
        const submitBtn = document.getElementById('register-submit-btn');
        if (isUnavailableDetectedToken() && !isDeveloperMode()) {
            await notifyUser('This pendant profile is already registered elsewhere, so user mode cannot overwrite it.', 'Registration Blocked');
            return;
        }
        if (uartBusy) {
            await notifyUser('Serial port is busy. Wait a moment and try again.', 'Serial Port Busy');
            return;
        }

        uartBusy = true;
        try {
            if (!(await ensureUartMode())) return;
            setButtonBusy(submitBtn, true, 'Provisioning...');
            appendHardwareLog(`Provisioning ${name}...`);

            const data = await postJson('/api/register', {
                name,
                ...hardwarePayload()
            });

            appendHardwareLog(data.reply || 'OK RESET_ALL');
            closeModal();
            await fetchDevices();
            selectDevice(data.device.id);
            await identifyConnectedToken({ silent: true, autoSelect: true, force: true });
        } catch (error) {
            appendHardwareLog(`Provisioning failed: ${error.message}`);
            await notifyUser(error.message, 'Provisioning Failed');
        } finally {
            uartBusy = false;
            setButtonBusy(submitBtn, false);
        }
    }

    async function renameActiveDevice() {
        if (!activeDeviceId) return;
        const device = devices.find((item) => item.id === activeDeviceId);
        if (!device) return;

        const name = await promptForPendantName(device.name);
        if (!name || name === device.name) return;

        try {
            const response = await fetch(`/api/devices/${activeDeviceId}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name })
            });
            const data = await parseJsonResponse(response);
            if (!response.ok || data.success === false) {
                throw new Error(data.error || 'Rename failed.');
            }

            appendHardwareLog(`Renamed pendant to ${name}.`);
            await fetchDevices();
            selectDevice(activeDeviceId);
        } catch (error) {
            appendHardwareLog(`Rename failed: ${error.message}`);
            await notifyUser(error.message, 'Rename Failed');
        }
    }

    function activeDevice() {
        return devices.find((item) => item.id === activeDeviceId) || null;
    }

    function textOrUnset(value) {
        const text = String(value ?? '').trim();
        return text || 'Not set';
    }

    function readPatientInfoFromDevice(device) {
        return {
            patient_name: device?.patient_name || '',
            patient_age: device?.patient_age ?? '',
            patient_phone: device?.patient_phone || '',
            patient_emergency_contact: device?.patient_emergency_contact || '',
            patient_allergies: device?.patient_allergies || '',
            patient_notes: device?.patient_notes || ''
        };
    }

    function setPatientModalMode(editing) {
        if (!patientReadView || !patientForm) return;
        patientReadView.classList.toggle('hidden', editing);
        patientForm.classList.toggle('hidden', !editing);
        if (editing && patientNameInput) {
            patientNameInput.focus();
        }
    }

    function populatePatientModal(device) {
        const info = readPatientInfoFromDevice(device);
        patientViewName.textContent = textOrUnset(info.patient_name);
        patientViewAge.textContent = info.patient_age === '' || info.patient_age === null
            ? 'Not set'
            : String(info.patient_age);
        patientViewPhone.textContent = textOrUnset(info.patient_phone);
        patientViewEmergency.textContent = textOrUnset(info.patient_emergency_contact);
        patientViewAllergies.textContent = textOrUnset(info.patient_allergies);
        patientViewNotes.textContent = textOrUnset(info.patient_notes);

        patientNameInput.value = info.patient_name;
        patientAgeInput.value = info.patient_age === null ? '' : String(info.patient_age);
        patientPhoneInput.value = info.patient_phone;
        patientEmergencyInput.value = info.patient_emergency_contact;
        patientAllergiesInput.value = info.patient_allergies;
        patientNotesInput.value = info.patient_notes;
    }

    async function openPatientModal() {
        const device = activeDevice();
        if (!device || !patientModal) return;

        populatePatientModal(device);
        setPatientModalMode(false);
        patientModal.classList.remove('hidden');
        if (patientEditBtn) patientEditBtn.focus();
    }

    function closePatientModal() {
        if (!patientModal) return;
        patientModal.classList.add('hidden');
        setPatientModalMode(false);
    }

    async function savePatientInfo(event) {
        event.preventDefault();
        const device = activeDevice();
        if (!device) return;

        const payload = {
            patient_name: patientNameInput.value.trim(),
            patient_age: patientAgeInput.value.trim(),
            patient_phone: patientPhoneInput.value.trim(),
            patient_emergency_contact: patientEmergencyInput.value.trim(),
            patient_allergies: patientAllergiesInput.value.trim(),
            patient_notes: patientNotesInput.value.trim()
        };

        try {
            setButtonBusy(patientSaveBtn, true, 'Saving...');
            const response = await fetch(`/api/devices/${device.id}/patient`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await parseJsonResponse(response);
            if (!response.ok || data.success === false) {
                throw new Error(data.error || 'Patient information update failed.');
            }

            const index = devices.findIndex((item) => item.id === device.id);
            if (index >= 0) {
                devices[index] = { ...devices[index], ...(data.patient || payload) };
                populatePatientModal(devices[index]);
            }
            setPatientModalMode(false);
            appendHardwareLog(`Updated patient information for ${device.name}.`);
        } catch (error) {
            appendHardwareLog(`Patient information update failed: ${error.message}`);
            await notifyUser(error.message, 'Patient Info Failed');
        } finally {
            setButtonBusy(patientSaveBtn, false);
        }
    }

    async function deleteDevice(id) {
        if (!id) {
            if (canDeveloperUnregisterUnknown()) {
                await unregisterUnknownPendant();
            }
            return;
        }

        const device = devices.find((item) => item.id === id);
        const deviceName = device?.name || 'This pendant';
        const isConnectedSelection = id === connectedDeviceId;
        let unregisterHardware = false;

        if (!isDeveloperMode() && !isConnectedSelection) {
            await notifyUser('Plug in this exact pendant so it can be cryptographically identified before deletion.', 'Delete Blocked');
            return;
        }

        if (isDeveloperMode()) {
            if (isConnectedSelection) {
                const scope = await chooseDeveloperDeleteScope(deviceName);
                if (!scope) return;
                unregisterHardware = scope === 'hardware';
            } else {
                if (!(await confirmDeveloperBackendOnlyDelete(deviceName))) return;
                unregisterHardware = false;
            }
        } else {
            if (!(await confirmUser('Delete this pendant and mark the plugged-in pendant as unregistered?', 'Delete Pendant', true, 'Delete'))) return;
            unregisterHardware = true;
        }

        if (unregisterHardware && uartBusy) {
            await notifyUser('Serial port is busy. Wait a moment and try again.', 'Serial Port Busy');
            return;
        }

        if (unregisterHardware) {
            uartBusy = true;
        }
        try {
            if (unregisterHardware && !(await ensureUartMode())) return;
            const response = await fetch(`/api/devices/${id}`, {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    ...hardwarePayload(),
                    require_hardware_verification: unregisterHardware
                })
            });
            const data = await parseJsonResponse(response);
            if (!response.ok) {
                await notifyUser(data.error || 'Delete failed.', 'Delete Failed');
                return;
            }
            if (activeDeviceId === id) {
                activeDeviceId = null;
                showEmptyState();
            }
            if (data.hardware_unregistered) {
                connectedDeviceId = null;
                detectedToken = { matched: false, provisioned: false, state: 'unregistered' };
            } else if (isConnectedSelection) {
                connectedDeviceId = null;
                detectedToken = { matched: false, provisioned: true, state: 'unknown_registered' };
            }
            await fetchDevices();
            renderDeviceList();
            appendHardwareLog(
                data.hardware_unregistered
                    ? 'Pendant deleted locally and marked unregistered on device.'
                    : 'Pendant deleted locally. Physical pendant was not changed.'
            );
        } catch (error) {
            appendHardwareLog(`Delete failed: ${error.message}`);
            await notifyUser(error.message, 'Delete Failed');
        } finally {
            if (unregisterHardware) {
                uartBusy = false;
            }
        }
    }

    async function unregisterUnknownPendant() {
        if (!canDeveloperUnregisterUnknown()) return;

        if (!(await confirmUnknownProfileReset())) {
            return;
        }
        if (uartBusy) {
            await notifyUser('Serial port is busy. Wait a moment and try again.', 'Serial Port Busy');
            return;
        }

        uartBusy = true;
        try {
            if (!(await ensureUartMode())) return;
            setPendantResetStatus('Resetting Pendant', 'running');
            appendHardwareLog('Resetting unknown registered pendant profile...');
            const data = await postJson('/api/token/unregister', hardwarePayload());
            appendHardwareLog(data.reply || 'OK UNREGISTER');
            connectedDeviceId = null;
            detectedToken = { matched: false, provisioned: false, state: 'unregistered' };
            renderDeviceList();
            updateHeaderActions();
            setPendantResetStatus('Pendant profile reset', 'success');
        } catch (error) {
            appendHardwareLog(`Unknown profile reset failed: ${error.message}`);
            setPendantResetStatus('Reset failed', 'error');
            await notifyUser(error.message, 'Reset Failed');
        } finally {
            uartBusy = false;
        }
    }

    async function resetDevice(action) {
        if (!activeDeviceId) return;
        if (activeDeviceId !== connectedDeviceId) {
            await notifyUser('Plug in this exact pendant so it can be cryptographically identified before resetting it.', 'Reset Blocked');
            return;
        }
        if (uartBusy) {
            await notifyUser('Serial port is busy. Wait a moment and try again.', 'Serial Port Busy');
            return;
        }

        uartBusy = true;
        const busyButton = action === 'reset_pendant' ? provisionKeyBtn : resetKeyBtn;
        try {
            if (!(await ensureUartMode())) return;
            const labels = {
                reset_default_key: 'Resetting pendant to the default key and resetting timer...',
                reset_pendant: 'Resetting Pendant'
            };
            const runningMessage = labels[action] || labels.reset_pendant;
            setButtonBusy(busyButton, true, 'Resetting...');
            setPendantResetStatus(runningMessage, 'running');
            appendHardwareLog(runningMessage);
            const data = await postJson(`/api/devices/${activeDeviceId}/reset`, {
                action,
                ...hardwarePayload()
            });
            appendHardwareLog(data.reply || 'Reset OK');
            await fetchDevices();
            selectDevice(activeDeviceId);
            await identifyConnectedToken({ silent: true, autoSelect: false, force: true });
            setPendantResetStatus(
                action === 'reset_default_key'
                    ? 'Default key and timer reset succeeded'
                    : 'Pendant reset succeeded',
                'success'
            );
        } catch (error) {
            appendHardwareLog(`Reset failed: ${error.message}`);
            setPendantResetStatus('Reset failed', 'error');
            await notifyUser(error.message, 'Reset Failed');
        } finally {
            uartBusy = false;
            setButtonBusy(busyButton, false);
        }
    }

    async function updateTOTP() {
        if (!activeDeviceId) return;

        try {
            const response = await fetch(`/api/devices/${activeDeviceId}/totp`);
            if (!response.ok) {
                showEmptyState();
                return;
            }
            const data = await parseJsonResponse(response);
            activeTimestep = data.timestep || 30;

            const codeStr = data.totp;
            totpCode.textContent = codeStr;
            const now = performance.now();
            const predictedElapsed = progressState
                ? progressState.elapsed + ((now - progressState.receivedAt) / 1000)
                : null;
            const shouldResync = !progressState ||
                progressState.timestep !== activeTimestep ||
                progressState.code !== codeStr ||
                Math.abs(predictedElapsed - data.elapsed) > 2;

            if (shouldResync) {
                progressState = {
                    elapsed: data.elapsed,
                    timestep: activeTimestep,
                    receivedAt: now,
                    code: codeStr
                };
            } else {
                progressState.code = codeStr;
            }

            if (statusTimestep) {
                statusTimestep.textContent = activeTimestep;
            }
        } catch (error) {
            console.error('Failed to update TOTP:', error);
        }
    }

    function renderDeviceList() {
        deviceList.innerHTML = '';
        devices.forEach((device) => {
            const li = document.createElement('li');
            li.className = [
                'device-item',
                device.id === activeDeviceId ? 'active' : '',
                device.id === connectedDeviceId ? 'connected' : ''
            ].filter(Boolean).join(' ');

            const icon = document.createElement('i');
            icon.dataset.feather = 'key';
            const label = document.createElement('span');
            label.textContent = device.name;

            li.appendChild(icon);
            li.appendChild(label);
            li.addEventListener('click', () => selectDevice(device.id));
            deviceList.appendChild(li);
        });

        if (detectedToken && !detectedToken.matched) {
            const li = document.createElement('li');
            const unavailable = isUnavailableDetectedToken() && !isDeveloperMode();
            li.className = [
                'device-item',
                unavailable ? 'unavailable-pendant' : 'pending-registration connected'
            ].join(' ');

            const icon = document.createElement('i');
            icon.dataset.feather = unavailable
                ? 'lock'
                : (detectedToken.provisioned ? 'alert-circle' : 'plus-circle');
            const label = document.createElement('span');
            label.textContent = unavailable
                ? 'Unavailable pendant'
                : (detectedToken.provisioned
                    ? 'Unknown registered pendant'
                    : 'Unregistered pendant');

            li.appendChild(icon);
            li.appendChild(label);
            if (canDeveloperUnregisterUnknown()) {
                const unregisterButton = document.createElement('button');
                unregisterButton.type = 'button';
                unregisterButton.className = 'inline-icon-btn danger';
                unregisterButton.title = 'Reset profile on pendant';
                const trashIcon = document.createElement('i');
                trashIcon.dataset.feather = 'trash-2';
                unregisterButton.appendChild(trashIcon);
                unregisterButton.addEventListener('click', (event) => {
                    event.stopPropagation();
                    unregisterUnknownPendant();
                });
                li.appendChild(unregisterButton);
            }
            if (!unavailable) {
                li.addEventListener('click', openModal);
            }
            deviceList.appendChild(li);
        }
        feather.replace();
    }

    function selectDevice(id) {
        activeDeviceId = id;
        renderDeviceList();
        updateHeaderActions();

        const device = devices.find((item) => item.id === id);
        if (!device) return;

        activeDeviceName.textContent = device.name;
        updateStatusKeyDisplay(device.secret_key);
        hideStatusKey();
        if (statusTimestep) {
            statusTimestep.textContent = device.timestep || 30;
        }
        if (statusElapsed) {
            statusElapsed.textContent = '0.0';
        }
        timestepSelect.value = String(device.timestep || selectedTimestep());
        progressState = null;

        showTOTPView();
        updateTOTP();

        if (totpInterval) clearInterval(totpInterval);
        totpInterval = setInterval(updateTOTP, 1000);
    }

    function showEmptyState() {
        emptyState.classList.remove('hidden');
        totpView.classList.add('hidden');
        progressState = null;
        updateHeaderActions();
        if (totpInterval) clearInterval(totpInterval);
    }

    function showTOTPView() {
        emptyState.classList.add('hidden');
        totpView.classList.remove('hidden');
    }

    function animateProgress() {
        if (progressState) {
            const elapsed = progressState.elapsed + ((performance.now() - progressState.receivedAt) / 1000);
            const remaining = Math.max(0, progressState.timestep - (elapsed % progressState.timestep));
            const percentage = progressState.timestep > 0 ? remaining / progressState.timestep : 0;
            progressCircle.style.strokeDashoffset = CIRCUMFERENCE - (percentage * CIRCUMFERENCE);
            progressCircle.classList.toggle('warning', remaining <= 5);
            if (statusElapsed) {
                statusElapsed.textContent = elapsed.toFixed(1);
            }
        }
        requestAnimationFrame(animateProgress);
    }

    async function openModal() {
        if (!detectedToken || detectedToken.matched) {
            await notifyUser('Plug in a pendant that is not already in the token list, then refresh/identify it before registering.', 'No New Pendant');
            return;
        }
        if (isUnavailableDetectedToken() && !isDeveloperMode()) {
            await notifyUser('This pendant profile is already registered elsewhere, so user mode cannot overwrite it.', 'Unavailable Pendant');
            return;
        }
        registerModal.classList.remove('hidden');
        deviceNameInput.value = '';
        deviceNameInput.focus();
    }

    function closeModal() {
        registerModal.classList.add('hidden');
    }

    developerModeBtn.addEventListener('click', () => setInterfaceMode('developer'));
    userModeBtn.addEventListener('click', () => setInterfaceMode('user'));
    addDeviceBtn.addEventListener('click', openModal);
    closeModalBtn.addEventListener('click', closeModal);
    if (editDeviceBtn) {
        editDeviceBtn.addEventListener('click', renameActiveDevice);
    }
    if (patientInfoBtn) {
        patientInfoBtn.addEventListener('click', openPatientModal);
    }
    if (closePatientModalBtn) {
        closePatientModalBtn.addEventListener('click', closePatientModal);
    }
    if (patientEditBtn) {
        patientEditBtn.addEventListener('click', () => setPatientModalMode(true));
    }
    if (patientCancelBtn) {
        patientCancelBtn.addEventListener('click', () => {
            const device = activeDevice();
            if (device) populatePatientModal(device);
            setPatientModalMode(false);
        });
    }
    if (patientForm) {
        patientForm.addEventListener('submit', savePatientInfo);
    }
    deleteDeviceBtn.addEventListener('click', () => {
        if (activeDeviceId) {
            deleteDevice(activeDeviceId);
        } else {
            unregisterUnknownPendant();
        }
    });
    if (statusKey) {
        statusKey.addEventListener('click', revealStatusKeyWithUart);
    }

    if (resetKeyBtn) {
        resetKeyBtn.addEventListener('click', async () => {
            if (await confirmUser('Set this pendant and backend record back to the default key, and reset its timer?', 'Reset to Default Key', true)) {
                await resetDevice('reset_default_key');
            }
        });
    }
    if (refreshHardwareBtn) {
        refreshHardwareBtn.addEventListener('click', fetchHardware);
    }
    tokenPortSelect.addEventListener('change', () => {
        hideStatusKey();
        connectedDeviceId = null;
        detectedToken = null;
        renderDeviceList();
        updateHeaderActions();
        if (interfaceMode === 'user') {
            syncControlPortToTokenPort();
            selectedMode = null;
            updateModeUi(null, false);
        }
        identifyConnectedToken({ silent: false, autoSelect: true });
    });
    modeUpdiBtn.addEventListener('click', () => setAdapterMode('UPDI'));
    modeUartBtn.addEventListener('click', () => setAdapterMode('UART'));
    flashFirmwareBtn.addEventListener('click', startFlash);
    tokenHelloBtn.addEventListener('click', () => tokenCommand('/api/token/hello', 'TEST UART'));
    tokenReadSerialBtn.addEventListener('click', readRtc);
    provisionKeyBtn.addEventListener('click', provisionNewKey);
    clearLogBtn.addEventListener('click', () => {
        hardwareLog.textContent = '';
    });

    registerModal.addEventListener('click', (event) => {
        if (event.target === registerModal) closeModal();
    });
    if (patientModal) {
        patientModal.addEventListener('click', (event) => {
            if (event.target === patientModal) closePatientModal();
        });
    }

    registerForm.addEventListener('submit', (event) => {
        event.preventDefault();
        const name = deviceNameInput.value.trim();
        if (name) registerDevice(name);
    });

    setInterfaceMode(interfaceMode);
    fetchHardware();
    fetchDevices();
    identifyInterval = setInterval(() => {
        identifyConnectedToken({ silent: true, autoSelect: true });
    }, 4000);
    requestAnimationFrame(animateProgress);
});
