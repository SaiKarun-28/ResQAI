import { useEffect, useRef, useState } from 'react';
import { Button } from '../ui/Button';
import { normalizeMapCoordinates } from './weather';

export function CrisisMap({ location, onLocationChange }) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const markerRef = useRef(null);
  const tilesRef = useRef(null);
  const selectionRef = useRef({ location, onLocationChange });
  const [status, setStatus] = useState('loading');
  const [tileError, setTileError] = useState(false);

  useEffect(() => {
    selectionRef.current = { location, onLocationChange };
    if (!mapRef.current) return;
    const point = [location.latitude, location.longitude];
    markerRef.current.setLatLng(point);
    if (!mapRef.current.getBounds().contains(point)) {
      mapRef.current.setView(point, mapRef.current.getZoom(), { animate: false });
    }
  }, [location, onLocationChange]);

  useEffect(() => {
    let disposed = false;
    let map;
    let tiles;
    let observer;
    const onTileError = () => { if (!disposed) setTileError(true); };
    const onClick = ({ latlng }) => {
      const next = normalizeMapCoordinates(latlng.lat, latlng.lng);
      if (next) selectionRef.current.onLocationChange(next);
    };

    // Leaflet accesses window at import time: load only after client mounting.
    import('leaflet').then((module) => {
      if (disposed) return;
      const L = module.default || module;
      const selected = selectionRef.current.location;
      const point = [selected.latitude, selected.longitude];
      map = L.map(containerRef.current, {
        center: point, zoom: 11, minZoom: 2, maxZoom: 19,
        scrollWheelZoom: false, zoomAnimation: false, fadeAnimation: false,
        markerZoomAnimation: false, attributionControl: false,
      });
      mapRef.current = map;
      tiles = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19, keepBuffer: 1, updateWhenIdle: true, noWrap: true,
        attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>',
      });
      tiles.on('tileerror', onTileError);
      tiles.addTo(map);
      tilesRef.current = tiles;
      markerRef.current = L.circleMarker(point, {
        radius: 9, color: '#101D2C', weight: 3,
        fillColor: '#E9A23B', fillOpacity: 1, interactive: false,
      }).addTo(map);
      map.on('click', onClick);
      if (typeof ResizeObserver !== 'undefined') {
        observer = new ResizeObserver(() => {
          if (!disposed) map.invalidateSize({ animate: false, pan: false });
        });
        observer.observe(containerRef.current);
      }
      setStatus('ready');
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

  const osmLocation = `https://www.openstreetmap.org/?mlat=${location.latitude}&mlon=${location.longitude}#map=11/${location.latitude}/${location.longitude}`;
  const issueLocation = `https://www.openstreetmap.org/note/new#map=11/${location.latitude}/${location.longitude}`;

  return (
    <section aria-labelledby="environmental-map-title" className="bg-panel border border-border-default rounded-lg overflow-hidden min-w-0">
      <div className="p-4 space-y-2">
        <h2 id="environmental-map-title" className="font-semibold">Environmental map</h2>
        <p id="weather-map-help" className="text-sm text-text-muted">Click the map to choose a weather location, or use the latitude and longitude fields. Keyboard users can pan with arrow keys and zoom with + / −.</p>
        <p className="text-xs text-accent-amber">Amber marker: selected WEATHER location only. No incident pins or responder tracking.</p>
        <p className="text-sm font-mono">{location.latitude.toFixed(6)}, {location.longitude.toFixed(6)}</p>
        {location.isExample && <p className="text-xs text-accent-amber">Berlin example only — not your location or an incident location.</p>}
      </div>
      <div ref={containerRef} className="weather-map" role="region" aria-label="OpenStreetMap weather location selector" aria-describedby="weather-map-help" />
      <div className="p-4 space-y-3 text-xs">
        <p className="weather-map-attribution">© <a className="underline" href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap contributors</a></p>
        {status === 'loading' && <p role="status" className="text-accent-amber">Loading map… Coordinate entry is available while the map loads.</p>}
        {status === 'error' && <p role="alert" className="text-red-300">The map could not load. Use coordinate entry for weather, open OpenStreetMap below, or reload the page to retry the map.</p>}
        {tileError && <div role="alert" className="space-y-2 text-red-300">
          <p>Some map tiles could not load. Weather and coordinate entry still work. You can also open OpenStreetMap below.</p>
          <Button variant="secondary" size="sm" onClick={() => { setTileError(false); tilesRef.current?.redraw(); }}>Retry map tiles</Button>
        </div>}
        <div className="flex flex-wrap gap-3 text-accent-amber">
          <a href={osmLocation} target="_blank" rel="noreferrer" className="underline">Open in OpenStreetMap</a>
          <a href={issueLocation} target="_blank" rel="noreferrer" className="underline">Report map issue</a>
        </div>
        <p className="text-text-muted">Map tiles are requested directly from OpenStreetMap. No browser geolocation or automatic GPS is used. Weather is separate from fictional emergency resources.</p>
      </div>
    </section>
  );
}
