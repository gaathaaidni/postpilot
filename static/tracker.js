/**
 * PostPilot First-Party Privacy-Preserving Telemetry Tracker (postpilot-tracker.js)
 * Lightweight (< 2KB), zero-cookie, client-side telemetry script for Gaatha ecosystem properties.
 * Collects navigation telemetry without storing raw IP addresses or personal identifiable information.
 */
(function() {
    'use strict';

    // 1. Locate current script tag and property key
    var currentScript = document.currentScript || (function() {
        var scripts = document.getElementsByTagName('script');
        return scripts[scripts.length - 1];
    })();

    var propertyKey = currentScript ? currentScript.getAttribute('data-property') : null;
    if (!propertyKey && window.POSTPILOT_PROPERTY_KEY) {
        propertyKey = window.POSTPILOT_PROPERTY_KEY;
    }
    if (!propertyKey) {
        // Silently exit if no property key is provided
        return;
    }

    // 2. Telemetry Ingestion Endpoint
    var endpoint = currentScript ? currentScript.getAttribute('data-endpoint') : null;
    if (!endpoint) {
        endpoint = 'https://postpilot.gaatha.tech/api/web-intel/collect';
    }

    // 3. Ephemeral Session ID via sessionStorage (Strictly zero persistent cookies)
    var sessionIdKey = '_pp_session_id';
    var sessionId = null;
    try {
        sessionId = sessionStorage.getItem(sessionIdKey);
        if (!sessionId) {
            sessionId = 's_' + Math.random().toString(36).substring(2, 12) + '_' + Date.now().toString(36);
            sessionStorage.setItem(sessionIdKey, sessionId);
        }
    } catch (e) {
        sessionId = 's_' + Math.random().toString(36).substring(2, 12);
    }

    // 4. Device & Screen Resolution Detection
    var width = window.innerWidth || (document.documentElement ? document.documentElement.clientWidth : 0) || screen.width || 0;
    var deviceType = 'desktop';
    if (width <= 768) {
        deviceType = 'mobile';
    } else if (width <= 1024) {
        deviceType = 'tablet';
    }

    // 5. Load Performance Timing
    var loadTimeMs = 0;
    if (window.performance && window.performance.timing) {
        var t = window.performance.timing;
        if (t.loadEventEnd > t.navigationStart) {
            loadTimeMs = t.loadEventEnd - t.navigationStart;
        }
    }

    // 6. Base Payload
    var basePayload = {
        property_key: propertyKey,
        session_id: sessionId,
        path: window.location.pathname || '/',
        query_string: window.location.search || '',
        page_title: document.title || '',
        referrer: document.referrer || '',
        screen_size: (screen.width || 0) + 'x' + (screen.height || 0),
        device_type: deviceType,
        load_time_ms: loadTimeMs,
        tz: (window.Intl && Intl.DateTimeFormat) ? Intl.DateTimeFormat().resolvedOptions().timeZone : ''
    };

    // 7. Beacon / Fetch Transport
    function sendTelemetry(data, eventType) {
        data.event_type = eventType || 'pageview';
        var body = JSON.stringify(data);
        if (navigator.sendBeacon) {
            var blob = new Blob([body], { type: 'application/json' });
            navigator.sendBeacon(endpoint, blob);
        } else if (window.fetch) {
            fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: body,
                keepalive: true,
                mode: 'cors'
            }).catch(function() {});
        }
    }

    // 8. Fire Initial Pageview Beacon
    if (document.readyState === 'complete') {
        setTimeout(function() { sendTelemetry(basePayload, 'pageview'); }, 100);
    } else {
        window.addEventListener('load', function() {
            setTimeout(function() { sendTelemetry(basePayload, 'pageview'); }, 100);
        });
    }

    // 9. Expose Global Helper API for Custom Events & Inbound Form Conversions
    window.postpilot = {
        trackEvent: function(category, name, label, extraData) {
            var eventPayload = Object.assign({}, basePayload, {
                event_type: 'event',
                event_category: category || 'general',
                event_name: name || 'action',
                event_label: label || '',
                event_data: extraData || {}
            });
            sendTelemetry(eventPayload, 'event');
        },
        trackConversion: function(conversionType, leadId, metadata) {
            var convPayload = Object.assign({}, basePayload, {
                event_type: 'conversion',
                conversion_type: conversionType || 'lead',
                lead_identifier: leadId || '',
                metadata: metadata || {}
            });
            sendTelemetry(convPayload, 'conversion');
        }
    };
})();
