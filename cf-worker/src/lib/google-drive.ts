/**
 * Minimal Google Drive API v3 client for Cloudflare Workers.
 *
 * Authenticates as a service account by self-signing a JWT with Web Crypto
 * (RS256) and exchanging it for an OAuth2 access token — no external auth
 * library needed, since Workers ships Web Crypto but not Node's `crypto`.
 */

export interface ServiceAccountKey {
  client_email: string;
  private_key: string;
}

export interface DriveFile {
  id: string;
  name: string;
  modifiedTime: string;
  md5Checksum?: string;
}

const TOKEN_URL = "https://oauth2.googleapis.com/token";
const DRIVE_API = "https://www.googleapis.com/drive/v3";
const SCOPE = "https://www.googleapis.com/auth/drive.readonly";
const TOKEN_TTL_SECONDS = 3600;

function base64UrlEncodeBytes(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function base64UrlEncodeJson(value: unknown): string {
  return base64UrlEncodeBytes(new TextEncoder().encode(JSON.stringify(value)));
}

function pemToPkcs8(pem: string): ArrayBuffer {
  const stripped = pem
    .replace(/-----BEGIN PRIVATE KEY-----/, "")
    .replace(/-----END PRIVATE KEY-----/, "")
    .replace(/\s+/g, "");
  const binary = atob(stripped);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes.buffer;
}

async function signJwt(key: ServiceAccountKey): Promise<string> {
  const nowSeconds = Math.floor(Date.now() / 1000);
  const header = { alg: "RS256", typ: "JWT" };
  const claims = {
    iss: key.client_email,
    scope: SCOPE,
    aud: TOKEN_URL,
    iat: nowSeconds,
    exp: nowSeconds + TOKEN_TTL_SECONDS
  };
  const unsigned = `${base64UrlEncodeJson(header)}.${base64UrlEncodeJson(claims)}`;

  const cryptoKey = await crypto.subtle.importKey(
    "pkcs8",
    pemToPkcs8(key.private_key),
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const signature = await crypto.subtle.sign(
    "RSASSA-PKCS1-v1_5",
    cryptoKey,
    new TextEncoder().encode(unsigned)
  );

  return `${unsigned}.${base64UrlEncodeBytes(new Uint8Array(signature))}`;
}

export async function getAccessToken(key: ServiceAccountKey): Promise<string> {
  const assertion = await signJwt(key);
  const res = await fetch(TOKEN_URL, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer",
      assertion
    })
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Google token exchange failed: ${res.status} ${text}`);
  }
  const body = (await res.json()) as { access_token: string };
  return body.access_token;
}

/** Lists every non-trashed file directly inside a Drive folder (single level, follows pagination). */
export async function listFolderFiles(accessToken: string, folderId: string): Promise<DriveFile[]> {
  const files: DriveFile[] = [];
  let pageToken: string | undefined;

  do {
    const params = new URLSearchParams({
      q: `'${folderId}' in parents and trashed = false`,
      fields: "nextPageToken, files(id, name, modifiedTime, md5Checksum)",
      pageSize: "1000"
    });
    if (pageToken) params.set("pageToken", pageToken);

    const res = await fetch(`${DRIVE_API}/files?${params.toString()}`, {
      headers: { Authorization: `Bearer ${accessToken}` }
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`Drive files.list failed: ${res.status} ${text}`);
    }
    const body = (await res.json()) as { files: DriveFile[]; nextPageToken?: string };
    files.push(...body.files);
    pageToken = body.nextPageToken;
  } while (pageToken);

  return files;
}

export async function downloadFile(accessToken: string, fileId: string): Promise<string> {
  const res = await fetch(`${DRIVE_API}/files/${fileId}?alt=media`, {
    headers: { Authorization: `Bearer ${accessToken}` }
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Drive files.get(${fileId}) failed: ${res.status} ${text}`);
  }
  return res.text();
}
