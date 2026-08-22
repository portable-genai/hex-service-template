// Security-header baseline at the Next.js document layer, mirroring the API-side
// hex_service_kit.web.add_security_headers. In secure/embedded mode set FRAME_ANCESTORS to the
// parent origins permitted to iframe this UI (never '*'); default is 'self'.
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const FRAME_ANCESTORS = process.env.NEXT_PUBLIC_FRAME_ANCESTORS ?? "'self'";

export function middleware(_request: NextRequest) {
  const response = NextResponse.next();
  response.headers.set("Content-Security-Policy", `frame-ancestors ${FRAME_ANCESTORS}`);
  if (FRAME_ANCESTORS === "'self'") {
    response.headers.set("X-Frame-Options", "SAMEORIGIN");
  }
  response.headers.set("X-Content-Type-Options", "nosniff");
  response.headers.set("Referrer-Policy", "no-referrer");
  return response;
}

export const config = {
  matcher: "/:path*",
};
