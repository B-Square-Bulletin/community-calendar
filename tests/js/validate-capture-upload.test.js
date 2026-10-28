// tests/js/validate-capture-upload.test.js — poster capture upload seam.
//
// WHY: capture-event now requires a signed-in user's token. The dialog must
// fail with a sign-in prompt, and must not upload, when the session is gone.
'use strict';
import { describe, it, expect, afterEach } from 'vitest';
import { loadShipped, readShipped } from './load-shipped.js';

loadShipped();

const realFetch = global.fetch;
const realResize = window.resizeImageFile;

afterEach(() => {
  global.fetch = realFetch;
  window.resizeImageFile = realResize;
  window.authSession = null;
});

describe('resizeAndUpload auth', () => {
  it('returns a sign-in error without a session', async () => {
    window.authSession = null;
    await expect(window.resizeAndUpload({}, 'https://example.com', 'key')).resolves.toEqual({
      error: 'Please sign in again to capture events',
    });
  });

  it('sends the session token', async () => {
    window.authSession = { access_token: 'token' };
    window.resizeImageFile = () =>
      Promise.resolve(new File(['x'], 'x.jpg', { type: 'image/jpeg' }));
    let headers;
    global.fetch = (_url, options) => {
      headers = options.headers;
      return Promise.resolve(new Response('{}', { status: 200 }));
    };
    await window.resizeAndUpload({}, 'https://example.com', 'key');
    expect(headers.Authorization).toBe('Bearer token');
  });

  it('maps a 401 response to the sign-in error', async () => {
    window.authSession = { access_token: 'expired' };
    window.resizeImageFile = () =>
      Promise.resolve(new File(['x'], 'x.jpg', { type: 'image/jpeg' }));
    global.fetch = () =>
      Promise.resolve(new Response('{"error":"Invalid authorization"}', { status: 401 }));
    await expect(window.resizeAndUpload({}, 'https://example.com', 'key')).resolves.toEqual({
      error: 'Please sign in again to capture events',
    });
  });

  it('maps a 413 response to the size error', async () => {
    window.authSession = { access_token: 'token' };
    window.resizeImageFile = () =>
      Promise.resolve(new File(['x'], 'x.jpg', { type: 'image/jpeg' }));
    global.fetch = () =>
      Promise.resolve(new Response('{"error":"Upload too large (max 10 MiB)"}', { status: 413 }));
    await expect(window.resizeAndUpload({}, 'https://example.com', 'key')).resolves.toEqual({
      error: 'File is too large (max 10 MiB)',
    });
  });

  it('maps a resize failure', async () => {
    window.authSession = { access_token: 'token' };
    window.resizeImageFile = () => Promise.reject(new Error('bad image'));
    await expect(window.resizeAndUpload({}, 'https://example.com', 'key')).resolves.toEqual({
      error: 'Upload failed: bad image',
    });
  });
});

describe('audio upload', () => {
  const audioFile = () => new File(['x'], 'memo.mp3', { type: 'audio/mpeg' });

  it('returns a sign-in error without a session', async () => {
    window.authSession = null;
    await expect(
      window.uploadAudioFile(audioFile(), 'https://example.com', 'key')
    ).resolves.toEqual({
      error: 'Please sign in again to capture events',
    });
  });

  it('sends the session token and form fields', async () => {
    window.authSession = { access_token: 'token' };
    const file = audioFile();
    let url;
    let options;
    global.fetch = (requestUrl, opts) => {
      url = requestUrl;
      options = opts;
      return Promise.resolve(new Response('{}', { status: 200 }));
    };
    await window.uploadAudioFile(file, 'https://example.com', 'key');
    expect(url).toBe('https://example.com/functions/v1/capture-event');
    expect(options.headers).toEqual({
      apikey: 'key',
      Authorization: 'Bearer token',
    });
    expect(options.body.get('mode')).toBe('extract');
    expect(options.body.get('timezone')).toBe('America/Los_Angeles');
    const sent = options.body.get('file');
    expect(sent.name).toBe('memo.mp3');
    expect(sent.type).toBe('audio/mpeg');
    expect(sent.size).toBe(1);
  });

  it('maps a 401 response to the sign-in error', async () => {
    window.authSession = { access_token: 'expired' };
    global.fetch = () =>
      Promise.resolve(new Response('{"error":"Invalid authorization"}', { status: 401 }));
    await expect(
      window.uploadAudioFile(audioFile(), 'https://example.com', 'key')
    ).resolves.toEqual({
      error: 'Please sign in again to capture events',
    });
  });

  it('maps a 413 response to the size error', async () => {
    window.authSession = { access_token: 'token' };
    global.fetch = () =>
      Promise.resolve(new Response('{"error":"Upload too large (max 10 MiB)"}', { status: 413 }));
    await expect(
      window.uploadAudioFile(audioFile(), 'https://example.com', 'key')
    ).resolves.toEqual({
      error: 'File is too large (max 10 MiB)',
    });
  });

  it('returns the extracted event and transcript', async () => {
    window.authSession = { access_token: 'token' };
    global.fetch = () =>
      Promise.resolve(
        new Response(
          JSON.stringify({ event: { title: 'Show' }, transcript: 'come see the show' }),
          { status: 200 }
        )
      );
    await expect(
      window.uploadAudioFile(audioFile(), 'https://example.com', 'key')
    ).resolves.toEqual({
      event: { title: 'Show' },
      transcript: 'come see the show',
    });
  });

  it('surfaces a server error', async () => {
    window.authSession = { access_token: 'token' };
    global.fetch = () => Promise.resolve(new Response('boom', { status: 500 }));
    await expect(
      window.uploadAudioFile(audioFile(), 'https://example.com', 'key')
    ).resolves.toEqual({
      error: 'Server error 500: boom',
    });
  });

  it('surfaces the server error message from JSON', async () => {
    window.authSession = { access_token: 'token' };
    global.fetch = () =>
      Promise.resolve(
        new Response(JSON.stringify({ error: 'Failed to extract event' }), { status: 500 })
      );
    await expect(
      window.uploadAudioFile(audioFile(), 'https://example.com', 'key')
    ).resolves.toEqual({
      error: 'Failed to extract event',
    });
  });

  it('surfaces a network failure', async () => {
    window.authSession = { access_token: 'token' };
    global.fetch = () => Promise.reject(new Error('offline'));
    await expect(
      window.uploadAudioFile(audioFile(), 'https://example.com', 'key')
    ).resolves.toEqual({
      error: 'Upload failed: offline',
    });
  });

  it('both dialog handlers call the tested upload helper', () => {
    const markup = readShipped('components/AudioCaptureDialog.xmlui');
    expect(markup.match(/window\.uploadAudioFile\(/g)).toHaveLength(2);
    expect(markup).not.toContain('Actions.upload');
  });
});
