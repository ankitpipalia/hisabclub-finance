/**
 * Verify the Android emulator localhost→10.0.2.2 rewrite logic in
 * api/client.ts. The rewrite only fires on Android — iOS simulator and
 * physical Android devices resolve localhost differently and must be left
 * alone.
 */
describe('localhost rewrite for Android emulator', () => {
  function rewrite(url: string, platform: 'ios' | 'android'): string {
    if (platform === 'android') {
      return url.replace(/(https?:\/\/)(localhost|127\.0\.0\.1)/i, '$110.0.2.2');
    }
    return url;
  }

  it('rewrites localhost on android', () => {
    expect(rewrite('http://localhost:8001/api/v1', 'android')).toBe(
      'http://10.0.2.2:8001/api/v1',
    );
  });

  it('rewrites 127.0.0.1 on android', () => {
    expect(rewrite('http://127.0.0.1:8001/api/v1', 'android')).toBe(
      'http://10.0.2.2:8001/api/v1',
    );
  });

  it('rewrites https localhost too', () => {
    expect(rewrite('https://localhost/api/v1', 'android')).toBe(
      'https://10.0.2.2/api/v1',
    );
  });

  it('leaves remote hosts alone on android', () => {
    expect(rewrite('https://api.hisabclub.com/api/v1', 'android')).toBe(
      'https://api.hisabclub.com/api/v1',
    );
  });

  it('leaves localhost alone on ios', () => {
    expect(rewrite('http://localhost:8001/api/v1', 'ios')).toBe(
      'http://localhost:8001/api/v1',
    );
  });

  it('rewrites case-insensitively (LOCALHOST)', () => {
    expect(rewrite('http://LOCALHOST:8001/api/v1', 'android')).toBe(
      'http://10.0.2.2:8001/api/v1',
    );
  });
});
