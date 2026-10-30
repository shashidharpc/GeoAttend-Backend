/**
 * QR Code Scanner Module
 * Handles camera-based and file-based QR code scanning
 */

class QRScanner {
    constructor(options = {}) {
        this.readerId = options.readerId || 'reader';
        this.onSuccess = options.onSuccess || this.defaultOnSuccess;
        this.onError = options.onError || this.defaultOnError;
        this.scanner = null;
        this.isScanning = false;
        
        // Scanner configuration
        this.config = {
            fps: 10,
            qrbox: { width: 250, height: 250 },
            aspectRatio: 1.0,
            ...options.config
        };
    }

    /**
     * Initialize the scanner
     */
    async init() {
        try {
            this.scanner = new Html5Qrcode(this.readerId);
            console.log('QR Scanner initialized');
        } catch (error) {
            console.error('Failed to initialize scanner:', error);
            this.onError('Failed to initialize QR scanner');
        }
    }

    /**
     * Start camera scanning
     */
    async startCameraScanning() {
        if (this.isScanning) {
            console.warn('Scanner already running');
            return;
        }

        try {
            // Get available cameras
            const devices = await Html5Qrcode.getCameras();
            
            if (!devices || devices.length === 0) {
                throw new Error('No cameras found on device');
            }

            // Prefer back camera for mobile devices
            const cameraId = this.selectCamera(devices);

            // Start scanning
            await this.scanner.start(
                cameraId,
                this.config,
                this.handleQrCodeSuccess.bind(this),
                this.handleQrCodeError.bind(this)
            );

            this.isScanning = true;
            console.log('Camera scanning started');
            
            // Update UI
            this.updateScannerUI(true);

        } catch (error) {
            console.error('Error starting camera:', error);
            this.onError(`Camera error: ${error.message}`);
        }
    }

    /**
     * Stop camera scanning
     */
    async stopCameraScanning() {
        if (!this.isScanning) {
            return;
        }

        try {
            await this.scanner.stop();
            this.isScanning = false;
            console.log('Camera scanning stopped');
            
            // Update UI
            this.updateScannerUI(false);
            
        } catch (error) {
            console.error('Error stopping camera:', error);
        }
    }

    /**
     * Scan from file
     */
    async scanFile(file) {
        if (!file) {
            this.onError('No file selected');
            return;
        }

        try {
            // Validate file type
            if (!file.type.match('image.*')) {
                throw new Error('Please select an image file');
            }

            // Validate file size (max 5MB)
            if (file.size > 5 * 1024 * 1024) {
                throw new Error('File size must be less than 5MB');
            }

            console.log('Scanning file:', file.name);
            
            const decodedText = await this.scanner.scanFile(file, true);
            this.handleQrCodeSuccess(decodedText);

        } catch (error) {
            console.error('Error scanning file:', error);
            this.onError(`File scan error: ${error.message || error}`);
        }
    }

    /**
     * Select appropriate camera (prefer back camera)
     */
    selectCamera(devices) {
        console.log('Available cameras:', devices);

        // Try to find back camera
        const backCamera = devices.find(device => 
            device.label.toLowerCase().includes('back') ||
            device.label.toLowerCase().includes('rear') ||
            device.label.toLowerCase().includes('environment')
        );

        if (backCamera) {
            console.log('Using back camera:', backCamera.label);
            return backCamera.id;
        }

        // Use first available camera
        console.log('Using default camera:', devices[0].label);
        return devices[0].id;
    }

    /**
     * Handle successful QR code scan
     */
    handleQrCodeSuccess(decodedText, decodedResult) {
        console.log('QR Code detected:', decodedText);
        
        // Stop scanning immediately after successful scan
        if (this.isScanning) {
            this.stopCameraScanning();
        }

        // Call success callback
        this.onSuccess(decodedText, decodedResult);
    }

    /**
     * Handle QR code scan errors
     */
    handleQrCodeError(error) {
        // Ignore common scanning errors (no QR code in frame)
        if (error.includes('NotFoundException')) {
            return;
        }
        
        console.warn('QR Scan error:', error);
    }

    /**
     * Update scanner UI
     */
    updateScannerUI(isScanning) {
        const startBtn = document.getElementById('startScan');
        const stopBtn = document.getElementById('stopScan');

        if (startBtn && stopBtn) {
            if (isScanning) {
                startBtn.classList.add('d-none');
                stopBtn.classList.remove('d-none');
            } else {
                startBtn.classList.remove('d-none');
                stopBtn.classList.add('d-none');
            }
        }
    }

    /**
     * Default success handler
     */
    defaultOnSuccess(decodedText) {
        console.log('QR Code scanned:', decodedText);
        alert('QR Code: ' + decodedText);
    }

    /**
     * Default error handler
     */
    defaultOnError(error) {
        console.error('Scanner error:', error);
        alert('Error: ' + error);
    }

    /**
     * Cleanup and destroy scanner
     */
    async destroy() {
        if (this.isScanning) {
            await this.stopCameraScanning();
        }
        
        if (this.scanner) {
            await this.scanner.clear();
            this.scanner = null;
        }
    }
}

/**
 * Initialize QR Scanner for attendance system
 */
function initAttendanceScanner() {
    // Create scanner instance
    const scanner = new QRScanner({
        readerId: 'reader',
        onSuccess: handleAttendanceScan,
        onError: showScanError,
        config: {
            fps: 10,
            qrbox: { width: 250, height: 250 }
        }
    });

    // Initialize scanner
    scanner.init();

    // Start scan button
    const startBtn = document.getElementById('startScan');
    if (startBtn) {
        startBtn.addEventListener('click', async () => {
            try {
                // Request location permission first
                await getGeolocation();
                showScanStatus('Location access granted. Starting camera...', 'success');
                
                await scanner.startCameraScanning();
                showScanStatus('Camera ready. Position QR code in the frame.', 'info');
            } catch (error) {
                showScanError(error.message);
            }
        });
    }

    // Stop scan button
    const stopBtn = document.getElementById('stopScan');
    if (stopBtn) {
        stopBtn.addEventListener('click', () => {
            scanner.stopCameraScanning();
            showScanStatus('Scanner stopped', 'secondary');
        });
    }

    // File upload
    const fileInput = document.getElementById('qr-file');
    if (fileInput) {
        fileInput.addEventListener('change', async (e) => {
            const file = e.target.files[0];
            if (file) {
                try {
                    // Request location permission
                    await getGeolocation();
                    showScanStatus('Processing image...', 'info');
                    
                    await scanner.scanFile(file);
                } catch (error) {
                    showScanError(error.message);
                }
            }
        });
    }

    // Cleanup on page unload
    window.addEventListener('beforeunload', () => {
        scanner.destroy();
    });

    return scanner;
}

/**
 * Handle attendance QR code scan
 */
async function handleAttendanceScan(qrData) {
    showScanStatus('Verifying attendance...', 'info');

    try {
        // Get current location
        const location = await getGeolocation();

        // Send to backend for verification
        const response = await fetch('/student/verify_attendance', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                qr_data: qrData,
                latitude: location.latitude,
                longitude: location.longitude
            })
        });

        const data = await response.json();

        if (data.success) {
            showScanStatus(data.message, 'success');
            
            // Redirect after 2 seconds
            setTimeout(() => {
                window.location.href = '/student/dashboard';
            }, 2000);
        } else {
            showScanError(data.message);
        }

    } catch (error) {
        console.error('Attendance verification error:', error);
        showScanError('Failed to verify attendance. Please try again.');
    }
}

/**
 * Show scan status message
 */
function showScanStatus(message, type = 'info') {
    const statusDiv = document.getElementById('status');
    if (!statusDiv) return;

    const icons = {
        success: 'fas fa-check-circle',
        error: 'fas fa-times-circle',
        danger: 'fas fa-exclamation-circle',
        warning: 'fas fa-exclamation-triangle',
        info: 'fas fa-info-circle',
        secondary: 'fas fa-stop-circle'
    };

    statusDiv.className = `alert alert-${type}`;
    statusDiv.innerHTML = `<i class="${icons[type] || icons.info} me-2"></i> ${message}`;
    statusDiv.classList.remove('d-none');
}

/**
 * Show scan error message
 */
function showScanError(message) {
    showScanStatus(message, 'danger');
}

// Export for global use
window.QRScanner = QRScanner;
window.initAttendanceScanner = initAttendanceScanner;