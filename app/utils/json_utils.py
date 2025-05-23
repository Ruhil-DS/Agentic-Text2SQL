import json
import decimal
from datetime import datetime, date

class DecimalEncoder(json.JSONEncoder):
    """
    Custom JSON encoder that can handle Decimal, datetime and date objects
    """
    def default(self, obj):
        if isinstance(obj, decimal.Decimal):
            return float(obj)
        elif isinstance(obj, (datetime, date)):
            return obj.isoformat()
        # Let the base class default method handle other types
        return super(DecimalEncoder, self).default(obj)

def dumps(obj, **kwargs):
    """
    Wrapper around json.dumps that handles Decimal objects
    """
    return json.dumps(obj, cls=DecimalEncoder, **kwargs)

def loads(s, **kwargs):
    """
    Wrapper around json.loads
    """
    return json.loads(s, **kwargs) 