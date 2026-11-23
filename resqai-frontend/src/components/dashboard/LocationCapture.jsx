import { useEffect, useRef, useState, useCallback } from 'react';
import { Button } from '../ui/Button';
import { normalizeMapCoordinates } from './weather';

const OSM_TILE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
const OSM_ATTRIBUTION = '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>';
const MAX_ACCURACY_METERS = 5000;

export function LocationCapture({ onLocationChange, initialLocation = null }) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const markerRef = useRef(null);
  const tilesRef = useRef(null);
  const selectionRef = useRef({ location: initialLocation, onLocationChange });

  const [status, setStatus] = useState('idle'); // idle | requesting | granted | denied | error | manual
  const [gpsLocation, setGpsLocation] = useState(null);
  const [manualLocation, setManualLocation] = useState(initialLocation);
  const [addressInput, setAddressInput] = useState('');
  const [tileError, setTileError] = useState(false);
  const [mapReady, setMapReady] = useState(false);
  const [useMapPin, setUseMapPin] = useState(false);

  // Keep refs updated
  useEffect(() => {
    selectionRef.current = { location: manualLocation, onLocationChange };
  }, [manualLocation, onLocationChange]);

  // Initialize map
  useEffect(() => {
    let disposed = false;
    let map, tiles, observer;

    const onTileError = () => { if (!disposed) setTileError(true); };
    const onClick = ({ latlng }) => {
      const next = normalizeMapCoordinates(latlng.lat, latlng.lng);
      if (next) {
        setManualLocation(next);
        setUseMapPin(true);
      }
    };

    import('leaflet').then((module) => {
      if (disposed) return;
      const L = module.default || module;
      const selected = selectionRef.current.location;
      const point = selected ? [selected.latitude, selected.longitude] : [28.6139, 77.2090]; // Default to Delhi
      const zoom = selected ? 13 : 11;

      map = L.map(containerRef.current, {
        center: point, zoom, minZoom: 2, maxZoom: 19,
        scrollWheelZoom: false, zoomAnimation: false, fadeAnimation: false,
        markerZoomAnimation: false, attributionControl: false,
      });
      mapRef.current = map;

      tiles = L.tileLayer(OSM_TILE_URL, {
        maxZoom: 19, keepBuffer: 1, updateWhenIdle: true, noWrap: true,
        attribution: OSM_ATTRIBUTION,
      });
      tiles.on('tileerror', onTileError);
      tiles.addTo(map);
      tilesRef.current = tiles;

      // Initial marker if location exists
      if (selected) {
        markerRef.current = L.circleMarker(point, {
          radius: 9, color: '#101D2C', weight: 3,
          fillColor: '#E9A23B', fillOpacity: 1, interactive: false,
        }).addTo(map);
      }

      map.on('click', onClick);

      if (typeof ResizeObserver !== 'undefined') {
        observer = new ResizeObserver(() => {
          if (!disposed) map.invalidateSize({ animate: false, pan: false });
        });
        observer.observe(containerRef.current);
      }

      setMapReady(true);
    }).catch(() => {
      if (disposed) return;
      observer?.disconnect();
      tiles?.off('tileerror', onTileError);
      map?.off('click', onClick);
      map?.remove();
      map = null;
      mapRef.current = null;
      markerRef.current = null;
      tilesRef.current = null;
      setMapReady(false);
      setStatus('error');
    });

    return () => {
      disposed = true;
      observer?.disconnect();
      tiles?.off('tileerror', onTileError);
      map?.off('click', onClick);
      map?.remove();
      mapRef.current = null;
      markerRef.current = null;
      tilesRef.current = null;
    };
  }, []);

  // Handle GPS request
  const requestGps = useCallback(async () => {
    if (!navigator.geolocation) {
      setStatus('error');
      return;
    }

    setStatus('requesting');
    try {
      const position = await new Promise((resolve, reject) => {
        navigator.geolocation.getCurrentPosition(resolve, reject, {
          enableHighAccuracy: true,
          timeout: 15000,
          maximumAge: 0,
        });
      });

      const coords = normalizeMapCoordinates(position.coords.latitude, position.coords.longitude);
      if (!coords) {
        setStatus('error');
        return;
      }

      const gpsData = {
        ...coords,
        accuracy: position.coords.accuracy,
        source: 'browser_gps',
        timestamp: new Date(position.timestamp).toISOString(),
      };

      if (gpsData.accuracy > MAX_ACCURACY_METERS) {
        setStatus('error');
        return;
      }

      setGpsLocation(gpsData);
      setStatus('granted');
    } catch (error) {
      if (error.code === error.PERMISSION_DENIED) {
        setStatus('denied');
      } else {
        setStatus('error');
      }
    }
  }, []);

  // Update manual location from address input (uses Open-Meteo geocoding)
  const handleAddressSearch = useCallback(async () => {
    if (!addressInput.trim()) return;
    setStatus('requesting');

    try {
      const response = await fetch(
        `https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(addressInput.trim())}&count=1&language=en&format=json`
      );
      const data = await response.json();

      if (data.results && data.results.length > 0) {
        const result = data.results[0];
        const coords = normalizeMapCoordinates(result.latitude, result.longitude);
        if (coords) {
          const manualData = {
            ...coords,
            accuracy: 1000, // approximate for geocoded address
            source: 'manual_text',
            timestamp: new Date().toISOString(),
          };
          setManualLocation(manualData);
          setUseMapPin(false);
          setStatus('manual');
        }
      } else {
        setStatus('error');
      }
    } catch (error) {
      setStatus('error');
    }
  }, [addressInput]);

  // Clear location
  const clearLocation = useCallback(() => {
    setGpsLocation(null);
    setManualLocation(null);
    setAddressInput('');
    setUseMapPin(false);
    setStatus('idle');
    onLocationChange?.(null);
  }, [onLocationChange]);

  // Determine current effective location
  const currentLocation = gpsLocation || manualLocation;

  // Notify parent when location changes
  useEffect(() => {
    if (currentLocation) {
      onLocationChange?.(currentLocation);
    }
  }, [currentLocation, onLocationChange]);

  // Update marker when manual location changes
  useEffect(() => {
    if (!mapRef.current || !manualLocation) return;
    const point = [manualLocation.latitude, manualLocation.longitude];
    if (markerRef.current) {
      markerRef.current.setLatLng(point);
    } else {
      import('leaflet').then((module) => {
        const L = module.default || module;
        markerRef.current = L.circleMarker(point, {
          radius: 9, color: '#101D2C', weight: 3,
          fillColor: '#E9A23B', fillOpacity: 1, interactive: false,
        }).addTo(mapRef.current);
      });
    }
    if (!mapRef.current.getBounds().contains(point)) {
      mapRef.current.setView(point, 13, { animate: true });
    }
  }, [manualLocation]);

  const getStatusText = () => {
    switch (status) {
      case 'requesting': return 'Getting your location…';
      case 'granted': return `GPS: ${gpsLocation.latitude.toFixed(6)}, ${gpsLocation.longitude.toFixed(6)} (±${Math.round(gpsLocation.accuracy)}m)`;
      case 'denied': return 'Permission denied. Use manual entry below.';
      case 'error': return 'Could not get location. Use manual entry below.';
      case 'manual': return `Manual: ${manualLocation.latitude.toFixed(6)}, ${manualLocation.longitude.toFixed(6)} (±${Math.round(manualLocation.accuracy)}m, ${manualLocation.source})`;
      default: return 'No location selected.';
    }
  };

  const getStatusClass = () => {
    switch (status) {
      case 'granted': return 'text-green-300';
      case 'requesting': return 'text-accent-amber';
      case 'denied':
      case 'error': return 'text-red-300';
      case 'manual': return 'text-blue-300';
      default: return 'text-text-muted';
    }
  };

  return (
    <section aria-labelledby="location-capture-title" className="bg-panel border border-border-default rounded-lg p-4 space-y-4">
      <h3 id="location-capture-title" className="font-semibold">Location (Optional)</h3>
      <p className="text-sm text-text-muted">
        Provide your location for better resource matching. GPS requires explicit permission.
        Manual entry works without GPS. All locations show accuracy and source.
      </p>

      {/* GPS Button */}
      <div className="space-y-2">
        <Button
          variant={status === 'granted' ? 'secondary' : 'primary'}
          size="md"
          onClick={requestGps}
          disabled={status === 'requesting' || status === 'granted'}
          className="w-full"
        >
          {status === 'requesting' ? (
            <>
              <svg className="animate-spin -ml-1 mr-2 h-4 w-4" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              Requesting location…
            </>
          ) : status === 'granted' ? (
            '✓ GPS Location Captured'
          ) : (
            '📍 Share My Location (GPS)'
          )}
        </Button>

        <p className={`text-sm ${getStatusClass()}`} role="status">{getStatusText()}</p>

        {status === 'denied' && (
          <p className="text-xs text-text-muted">
            Browser blocked GPS access. Check site permissions or use manual entry.
          </p>
        )}
      </div>

      {/* Manual Entry - Address Search */}
      <div className="space-y-2 border-t border-border-default pt-4">
        <label htmlFor="address-input" className="block text-sm font-medium">Search by Address</label>
        <div className="flex gap-2">
          <input
            id="address-input"
            type="text"
            placeholder="Enter address, landmark, or place name"
            value={addressInput}
            onChange={(e) => setAddressInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleAddressSearch()}
            className="flex-1 bg-surface border border-border-default rounded-lg p-2 text-white"
          />
          <Button
            variant="secondary"
            size="sm"
            onClick={handleAddressSearch}
            disabled={status === 'requesting' || !addressInput.trim()}
          >
            Search
          </Button>
        </div>
        <p className="text-xs text-text-muted">Uses Open-Meteo geocoding (free, no key). Accuracy ~1km.</p>
      </div>

      {/* Manual Entry - Map Pin */}
      <div className="space-y-2 border-t border-border-default pt-4">
        <label className="block text-sm font-medium">Or Click Map to Place Pin</label>
        <p className="text-xs text-text-muted">Click anywhere on the map to set location manually.</p>
        <div
          ref={containerRef}
          className="crisis-map"
          role="region"
          aria-label="OpenStreetMap manual location selector"
          style={{ minHeight: '250px', width: '100%' }}
        />
        <div className="flex flex-wrap gap-2 text-xs">
          <p className="text-text-muted">Tiles: {OSM_ATTRIBUTION}</p>
          {tileError && (
            <div className="flex gap-2 text-red-300">
              <p>Some map tiles failed.</p>
              <Button variant="secondary" size="xs" onClick={() => { setTileError(false); tilesRef.current?.redraw(); }}>
                Retry
              </Button>
            </div>
          )}
        </div>
      </div>

      {/* Current Location Display */}
      {currentLocation && (
        <div className="bg-surface border border-border-default rounded-lg p-3 space-y-1">
          <p className="font-medium text-sm">Selected Location:</p>
          <p className="font-mono text-sm">
            {currentLocation.latitude.toFixed(6)}, {currentLocation.longitude.toFixed(6)}
          </p>
          <p className="text-xs text-text-muted">
            Accuracy: ±{Math.round(currentLocation.accuracy)}m • Source: {currentLocation.source}
            {currentLocation.timestamp && ` • Captured: ${new Date(currentLocation.timestamp).toLocaleString()}`}
          </p>
          <Button variant="ghost" size="sm" onClick={clearLocation}>Clear Location</Button>
        </div>
      )}

      {!currentLocation && (
        <p className="text-xs text-text-muted text-center py-2">
          No location provided. The report will use text-extracted location only.
        </p>
      )}
    </section>
  );
}