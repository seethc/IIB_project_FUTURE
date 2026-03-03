document.addEventListener('DOMContentLoaded', () => {
    // --- Elements ---
    const deviceList = document.getElementById('device-list');
    const emptyState = document.getElementById('empty-state');
    const totpView = document.getElementById('totp-view');
    const activeDeviceName = document.getElementById('active-device-name');
    const totpCode = document.getElementById('totp-code');
    const progressCircle = document.getElementById('progress-circle');
    
    const addDeviceBtn = document.getElementById('add-device-btn');
    const deleteDeviceBtn = document.getElementById('delete-device-btn');
    const registerModal = document.getElementById('register-modal');
    const closeModalBtn = document.querySelector('.close-modal');
    const registerForm = document.getElementById('register-form');
    const deviceNameInput = document.getElementById('device-name');

    // --- State ---
    let devices = [];
    let activeDeviceId = null;
    let totpInterval = null;
    const TIMESTEP = 30; // 30 seconds
    const CIRCUMFERENCE = 2 * Math.PI * 45; // r=45

    // Initialize progress circle dasharray
    progressCircle.style.strokeDasharray = CIRCUMFERENCE;

    // --- API Calls ---
    async function fetchDevices() {
        try {
            const response = await fetch('/api/devices');
            const data = await response.json();
            devices = data.devices;
            renderDeviceList();
        } catch (error) {
            console.error('Failed to fetch devices:', error);
        }
    }

    async function registerDevice(name) {
        try {
            const submitBtn = document.getElementById('register-submit-btn');
            submitBtn.textContent = 'Registering...';
            submitBtn.disabled = true;

            const response = await fetch('/api/register', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name })
            });
            const data = await response.json();
            
            if (data.success) {
                if (!data.device.uart_success) {
                    // Just log it or show a subtle notification. It will likely fail locally 
                    // on the laptop because there's no UART device attached.
                    console.warn("UART transmission failed. Token added to DB but ATtiny wasn't provisioned hardware-side.");
                }
                closeModal();
                await fetchDevices();
                selectDevice(data.device.id);
            }
        } catch (error) {
            console.error('Registration failed:', error);
            alert("Registration failed. See console.");
        } finally {
            const submitBtn = document.getElementById('register-submit-btn');
            submitBtn.textContent = 'Provision Device';
            submitBtn.disabled = false;
        }
    }

    async function deleteDevice(id) {
        if (!confirm('Are you sure you want to delete this token?')) return;
        try {
            await fetch(`/api/devices/${id}`, { method: 'DELETE' });
            if (activeDeviceId === id) {
                activeDeviceId = null;
                showEmptyState();
            }
            fetchDevices();
        } catch (error) {
            console.error('Failed to delete:', error);
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
            const data = await response.json();
            
            // Format code: add space in middle (e.g. 123 456)
            const codeStr = data.totp;
            totpCode.textContent = `${codeStr.slice(0, 3)} ${codeStr.slice(3)}`;
            
            // Update progress circle
            const percentage = data.remaining / TIMESTEP;
            const offset = CIRCUMFERENCE - (percentage * CIRCUMFERENCE);
            progressCircle.style.strokeDashoffset = offset;

            // Turn circle red if code is about to expire (< 5s)
            if (data.remaining <= 5) {
                progressCircle.classList.add('warning');
            } else {
                progressCircle.classList.remove('warning');
            }

        } catch (error) {
            console.error('Failed to update TOTP:', error);
        }
    }

    // --- UI Logic ---
    function renderDeviceList() {
        deviceList.innerHTML = '';
        devices.forEach(device => {
            const li = document.createElement('li');
            li.className = `device-item ${device.id === activeDeviceId ? 'active' : ''}`;
            li.innerHTML = `
                <i data-feather="key"></i>
                <span>${device.name}</span>
            `;
            li.addEventListener('click', () => selectDevice(device.id));
            deviceList.appendChild(li);
        });
        feather.replace();
    }

    function selectDevice(id) {
        activeDeviceId = id;
        renderDeviceList();
        
        const device = devices.find(d => d.id === id);
        if (device) {
            activeDeviceName.textContent = device.name;
            showTOTPView();
            updateTOTP(); // fetch immediately
            
            if (totpInterval) clearInterval(totpInterval);
            totpInterval = setInterval(updateTOTP, 1000); // refresh every second
        }
    }

    function showEmptyState() {
        emptyState.classList.remove('hidden');
        totpView.classList.add('hidden');
        if (totpInterval) clearInterval(totpInterval);
    }

    function showTOTPView() {
        emptyState.classList.add('hidden');
        totpView.classList.remove('hidden');
    }

    function openModal() {
        registerModal.classList.remove('hidden');
        deviceNameInput.value = '';
        deviceNameInput.focus();
    }

    function closeModal() {
        registerModal.classList.add('hidden');
    }

    // --- Event Listeners ---
    addDeviceBtn.addEventListener('click', openModal);
    closeModalBtn.addEventListener('click', closeModal);
    deleteDeviceBtn.addEventListener('click', () => deleteDevice(activeDeviceId));
    
    registerModal.addEventListener('click', (e) => {
        if (e.target === registerModal) closeModal();
    });

    registerForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const name = deviceNameInput.value.trim();
        if (name) registerDevice(name);
    });

    // Initial load
    fetchDevices();
});
