export async function proxyVps(): Promise<{
  ok: boolean;
  status: number;
  json: string;
  error: string;
}> {
  return { ok: false, status: 0, json: "{}", error: "No server proxy in the Android app" };
}
