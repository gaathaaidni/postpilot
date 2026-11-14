"""
PostPilot GeoIP Resolution Service (geoip_service.py)
Provides secure, offline, privacy-first approximate IP geolocation without third-party API dependencies.
Strictly avoids timezone-based city fabrication.
"""
import ipaddress
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Configurable path to offline MaxMind GeoLite2 database (.mmdb)
GEOIP_DB_PATH = os.environ.get(
    'POSTPILOT_GEOIP_DB_PATH',
    str(Path(__file__).parent / 'data' / 'GeoLite2-City.mmdb')
)

_reader = None
_reader_initialized = False


def _get_reader():
    """Lazily initializes the MaxMind database reader if the library and database exist."""
    global _reader, _reader_initialized
    if _reader_initialized:
        return _reader

    _reader_initialized = True
    if not os.path.exists(GEOIP_DB_PATH):
        logger.debug(f"GeoIP database file not found at {GEOIP_DB_PATH}. Offline GeoIP lookup unavailable.")
        _reader = None
        return None

    try:
        import maxminddb
        _reader = maxminddb.open_database(GEOIP_DB_PATH)
        logger.info(f"Initialized MaxMind GeoIP database from {GEOIP_DB_PATH}")
    except ImportError:
        logger.debug("maxminddb module not installed. Run 'pip install maxminddb' to enable MaxMind lookups.")
        _reader = None
    except Exception as e:
        logger.error(f"Failed to open GeoIP database at {GEOIP_DB_PATH}: {e}")
        _reader = None

    return _reader


def resolve_ip_location(ip_str: Optional[str]) -> Dict[str, Any]:
    """
    Resolves an IP address to approximate geographic details.
    
    Guarantees:
    - Never fabricates cities or states based on browser timezone.
    - Accurately classifies local, private, and loopback IP ranges.
    - If an offline database is not installed, returns clean 'Unknown' markers.
    - Returns approximate IP geolocation, clearly distinguished from physical GPS location.
    """
    if not ip_str or not isinstance(ip_str, str):
        return _unresolved_result()

    ip_clean = ip_str.strip()

    # 1. Parse and validate IP format
    try:
        ip_obj = ipaddress.ip_address(ip_clean)
    except ValueError:
        return _unresolved_result()

    # 2. Loopback and Private IP ranges (RFC 1918, RFC 4193, loopback)
    if ip_obj.is_loopback or ip_obj.is_private or ip_obj.is_reserved or ip_obj.is_link_local:
        return {
            'country_code': 'LO',
            'country_name': 'Local Network',
            'region_name': None,
            'city_name': 'Private / Loopback',
            'asn_org': None,
            'is_approximate': True,
            'is_internal': True,
            'source': 'internal'
        }

    # 3. MaxMind GeoLite2 lookup if database is installed
    reader = _get_reader()
    if reader is not None:
        try:
            record = reader.get(ip_clean)
            if record:
                country_data = record.get('country', {}) or record.get('registered_country', {})
                subdivisions = record.get('subdivisions', [])
                city_data = record.get('city', {})
                traits = record.get('traits', {})

                c_code = country_data.get('iso_code', 'XX')
                c_name = country_data.get('names', {}).get('en', 'Unknown')
                r_name = subdivisions[0].get('names', {}).get('en') if subdivisions else None
                city_name = city_data.get('names', {}).get('en')
                asn_org = traits.get('autonomous_system_organization')

                return {
                    'country_code': c_code,
                    'country_name': c_name,
                    'region_name': r_name,
                    'city_name': city_name,
                    'asn_org': asn_org,
                    'is_approximate': True,
                    'is_internal': False,
                    'source': 'maxmind_geolite2'
                }
        except Exception as e:
            logger.warning(f"Error querying GeoIP database for {ip_clean}: {e}")

    # 4. Fallback: Report unresolved location without fabricating data
    return _unresolved_result()


def _unresolved_result() -> Dict[str, Any]:
    """Standardized representation for unresolved or unconfigured external IP lookups."""
    return {
        'country_code': 'XX',
        'country_name': 'Unknown',
        'region_name': None,
        'city_name': None,
        'asn_org': None,
        'is_approximate': True,
        'is_internal': False,
        'source': 'unresolved'
    }


def get_geoip_status() -> Dict[str, Any]:
    """Returns the operational status of the GeoIP subsystem for diagnostic reporting."""
    db_exists = os.path.exists(GEOIP_DB_PATH)
    module_installed = False
    try:
        import maxminddb  # noqa
        module_installed = True
    except ImportError:
        pass

    return {
        'database_path': GEOIP_DB_PATH,
        'database_exists': db_exists,
        'module_installed': module_installed,
        'is_active': (db_exists and module_installed),
        'provider': 'MaxMind GeoLite2' if (db_exists and module_installed) else 'None (Unresolved fallback)'
    }
