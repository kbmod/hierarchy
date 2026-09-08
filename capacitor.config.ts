import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "app.kbmod.hierarchy",
  appName: "Hierarchy",
  webDir: "android-web",
  server: {
    androidScheme: "https",
    cleartext: true,
  },
  android: {
    allowMixedContent: true,
    backgroundColor: "#0c0c0d",
  },
  plugins: {
    CapacitorHttp: {
      enabled: true,
    },
  },
};

export default config;
