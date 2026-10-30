import qrcode
from io import BytesIO
import base64
import json
from math import radians, cos, sin, asin, sqrt
from datetime import datetime
import pytz

def generate_qr_code(data):
    """Generate QR code and return as base64 string"""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    
    # Convert data to JSON string
    qr_data = json.dumps(data)
    qr.add_data(qr_data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert to base64
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    
    return f"data:image/png;base64,{img_str}"

def calculate_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great circle distance between two points 
    on the earth (specified in decimal degrees)
    Returns distance in meters
    """
    # Convert decimal degrees to radians
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    
    # Haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    
    # Radius of earth in meters
    r = 6371000
    
    return c * r

def generate_random_password(length=8):
    """Generate a random password"""
    import random
    import string
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for i in range(length))

def format_datetime(dt):
    """Format datetime for display in IST"""
    if isinstance(dt, str):
        return dt
    if dt:
        # Convert UTC to IST
        ist = pytz.timezone('Asia/Kolkata')
        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt)
        dt_ist = dt.astimezone(ist)
        return dt_ist.strftime("%Y-%m-%d %H:%M:%S")
    return ""