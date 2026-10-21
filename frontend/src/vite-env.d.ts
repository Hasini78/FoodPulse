/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_GOOGLE_MAPS_API_KEY?: string
  readonly VITE_API_BASE_URL?: string
  readonly VITE_REQUIRE_AUTH?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
