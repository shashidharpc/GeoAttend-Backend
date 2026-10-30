/**
 * Geolocation Module
 * Handles GPS location detection and validation
 */

// Geolocation configuration
const GeoConfig = {
    timeout: 10000,        // 10 seconds
    maximumAge: 5000,      // 5 seconds
    enableHighAccuracy: true
};

/**
 * Get current geolocation
 * @returns {Promise<Object>} Location object with latitude and longitude
 */
function getGeolocation() {
    return new Promise((resolve, reject) => {
        // Check if geolocation is supported
        if (!navigator.geolocation) {
            reject(new Error('Geolocation is not supported by your browser'));
            return;
        }

        // Show loading state
        showLocationStatus('Getting your location...', 'info');

        // Get current position
        navigator.geolocation.getCurrentPosition(
            (position) => {
                const location = {
                    latitude: position.coords.latitude,
                    longitude: position.coords.longitude,
                    accuracy: position.coords.accuracy,
                    timestamp: new Date(position.timestamp)
                };

                console.log('Location obtained:', location);
                showLocationStatus('Location obtained successfully', 'success');
                
                resolve(location);
            },
            (error) => {
                console.error('Geolocation error:', error);
                
                let errorMessage = 'Unable to get your location. ';
                
                switch(error.code) {
                    case error.PERMISSION_DENIED:
                        errorMessage += 'Please allow location access in your browser settings.';
                        break;
                    case error.POSITION_UNAVAILABLE:
                        errorMessage += 'Location information is unavailable. Please check your device settings.';
                        break;
                    case error.TIMEOUT:
                        errorMessage += 'Location request timed out. Please try again.';
                        break;
                    default:
                        errorMessage += 'An unknown error occurred.';
                }
                
                showLocationStatus(errorMessage, 'danger');
                reject(new Error(errorMessage));
            },
            GeoConfig
        );
    });
}

/**
 * Watch geolocation changes
 * @param {Function} callback Function to call when position changes
 * @returns {Number} Watch ID
 */
function watchGeolocation(callback) {
    if (!navigator.geolocation) {
        console.error('Geolocation not supported');
        return null;
    }

    const watchId = navigator.geolocation.watchPosition(
        (position) => {
            const location = {
                latitude: position.coords.latitude,
                longitude: position.coords.longitude,
                accuracy: position.coords.accuracy,
                timestamp: new Date(position.timestamp)
            };
            
            callback(location);
        },
        (error) => {
            console.error('Watch position error:', error);
        },
        GeoConfig
    );

    return watchId;
}

/**
 * Clear geolocation watch
 * @param {Number} watchId Watch ID to clear
 */
function clearGeolocationWatch(watchId) {
    if (watchId && navigator.geolocation) {
        navigator.geolocation.clearWatch(watchId);
    }
}

/**
 * Calculate distance between two coordinates (Haversine formula)
 * @param {Number} lat1 Latitude of first point
 * @param {Number} lon1 Longitude of first point
 * @param {Number} lat2 Latitude of second point
 * @param {Number} lon2 Longitude of second point
 * @returns {Number} Distance in meters
 */
function calculateDistance(lat1, lon1, lat2, lon2) {
    const R = 6371000; // Earth's radius in meters
    
    const φ1 = lat1 * Math.PI / 180;
    const φ2 = lat2 * Math.PI / 180;
    const Δφ = (lat2 - lat1) * Math.PI / 180;
    const Δλ = (lon2 - lon1) * Math.PI / 180;

    const a = Math.sin(Δφ/2) * Math.sin(Δφ/2) +
              Math.cos(φ1) * Math.cos(φ2) *
              Math.sin(Δλ/2) * Math.sin(Δλ/2);
    
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));

    const distance = R * c; // Distance in meters
    
    return Math.round(distance * 100) / 100; // Round to 2 decimal places
}

/**
 * Check if user is within geofence radius
 * @param {Number} userLat User's latitude
 * @param {Number} userLon User's longitude
 * @param {Number} targetLat Target latitude
 * @param {Number} targetLon Target longitude
 * @param {Number} radius Radius in meters (default: 30)
 * @returns {Object} Result with isWithin flag and distance
 */
function isWithinGeofence(userLat, userLon, targetLat, targetLon, radius = 30) {
    const distance = calculateDistance(userLat, userLon, targetLat, targetLon);
    
    return {
        isWithin: distance <= radius,
        distance: distance,
        radius: radius
    };
}

/**
 * Get location accuracy description
 * @param {Number} accuracy Accuracy in meters
 * @returns {String} Accuracy description
 */
function getAccuracyDescription(accuracy) {
    if (accuracy <= 10) return 'Excellent';
    if (accuracy <= 20) return 'Good';
    if (accuracy <= 50) return 'Fair';
    if (accuracy <= 100) return 'Poor';
    return 'Very Poor';
}

/**
 * Show location status message
 * @param {String} message Status message
 * @param {String} type Alert type (success, info, warning, danger)
 */
function showLocationStatus(message, type = 'info') {
    const statusDiv = document.getElementById('locationStatus');
    if (!statusDiv) return;

    const icons = {
        success: 'fas fa-check-circle',
        info: 'fas fa-info-circle',
        warning: 'fas fa-exclamation-triangle',
        danger: 'fas fa-exclamation-circle'
    };

    statusDiv.className = `alert alert-${type}`;
    statusDiv.innerHTML = `<i class="${icons[type]} me-2"></i> ${message}`;
    statusDiv.classList.remove('d-none');
}

/**
 * Request location permission
 * @returns {Promise<String>} Permission state
 */
async function requestLocationPermission() {
    if (!navigator.permissions) {
        return 'unknown';
    }

    try {
        const result = await navigator.permissions.query({ name: 'geolocation' });
        return result.state; // 'granted', 'denied', or 'prompt'
    } catch (error) {
        console.error('Permission query error:', error);
        return 'unknown';
    }
}

/**
 * Get location with fallback to IP-based location
 * @returns {Promise<Object>} Location object
 */
async function getLocationWithFallback() {
    try {
        // Try GPS first
        const location = await getGeolocation();
        return location;
    } catch (error) {
        console.warn('GPS failed, trying IP-based location...');
        
        try {
            // Fallback to IP-based location
            const response = await fetch('https://ipapi.co/json/');
            const data = await response.json();
            
            return {
                latitude: data.latitude,
                longitude: data.longitude,
                accuracy: 5000, // IP-based is very inaccurate
                source: 'ip'
            };
        } catch (ipError) {
            console.error('IP location also failed:', ipError);
            throw new Error('Could not determine location');
        }
    }
}

/**
 * Format coordinates for display
 * @param {Number} lat Latitude
 * @param {Number} lon Longitude
 * @returns {String} Formatted coordinates
 */
function formatCoordinates(lat, lon) {
    const latDir = lat >= 0 ? 'N' : 'S';
    const lonDir = lon >= 0 ? 'E' : 'W';
    
    return `${Math.abs(lat).toFixed(6)}° ${latDir}, ${Math.abs(lon).toFixed(6)}° ${lonDir}`;
}

/**
 * Get Google Maps URL for coordinates
 * @param {Number} lat Latitude
 * @param {Number} lon Longitude
 * @returns {String} Google Maps URL
 */
function getGoogleMapsUrl(lat, lon) {
    return `https://www.google.com/maps?q=${lat},${lon}`;
}

/**
 * Open location in Google Maps
 * @param {Number} lat Latitude
 * @param {Number} lon Longitude
 */
function openInGoogleMaps(lat, lon) {
    window.open(getGoogleMapsUrl(lat, lon), '_blank');
}

/**
 * Auto-fill location inputs
 * @param {Number} lat Latitude
 * @param {Number} lon Longitude
 */
function fillLocationInputs(lat, lon) {
    const latInput = document.getElementById('latitude');
    const lonInput = document.getElementById('longitude');
    
    if (latInput) latInput.value = lat;
    if (lonInput) lonInput.value = lon;
}

/**
 * Initialize location button for classroom form
 */
function initLocationButton() {
    const btn = document.querySelector('[onclick*="getCurrentLocation"]');
    if (!btn) return;

    btn.addEventListener('click', async function(e) {
        e.preventDefault();
        
        try {
            const location = await getGeolocation();
            fillLocationInputs(location.latitude, location.longitude);
            
            showLocationStatus(
                `Location captured! Accuracy: ${getAccuracyDescription(location.accuracy)} (±${Math.round(location.accuracy)}m)`,
                'success'
            );
        } catch (error) {
            showLocationStatus(error.message, 'danger');
        }
    });
}

// Auto-initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    initLocationButton();
});

// Export functions for global use
window.getGeolocation = getGeolocation;
window.watchGeolocation = watchGeolocation;
window.clearGeolocationWatch = clearGeolocationWatch;
window.calculateDistance = calculateDistance;
window.isWithinGeofence = isWithinGeofence;
window.getAccuracyDescription = getAccuracyDescription;
window.requestLocationPermission = requestLocationPermission;
window.getLocationWithFallback = getLocationWithFallback;
window.formatCoordinates = formatCoordinates;
window.getGoogleMapsUrl = getGoogleMapsUrl;
window.openInGoogleMaps = openInGoogleMaps;
window.fillLocationInputs = fillLocationInputs;