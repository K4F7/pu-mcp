import { describe, expect, test } from 'bun:test';
import { loginSchoolPayload } from '../src/pu_tool/web_static/login_input';

describe('loginSchoolPayload', () => {
  test('sends a numeric school SID directly', () => {
    expect(loginSchoolPayload(' 237791864815616 ')).toEqual({
      sid: '237791864815616',
    });
  });

  test('sends an encoded SID or class URL for server-side decoding', () => {
    expect(loginSchoolPayload('QVpTRFBVS19QS1hRRVhS')).toEqual({
      encoded_sid: 'QVpTRFBVS19QS1hRRVhS',
    });
    const url = 'https://class.pocketuni.net/#/login?sid=QVpTRFBVS19QS1hRRVhS';
    expect(loginSchoolPayload(url)).toEqual({ encoded_sid: url });
  });

  test('rejects an empty school identifier', () => {
    expect(() => loginSchoolPayload('   ')).toThrow('请输入学校 SID');
  });
});
