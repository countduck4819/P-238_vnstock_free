// export const runtime = "nodejs";
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import jwt from "jsonwebtoken";
import { Role } from "./share/enum";
import { publicRouters } from "./share/const/const";

const SECRET_KEY = process.env.JWT_SECRET || "123456789";
// Middleware chạy phía server nên gọi thẳng NestJS (giống rewrite /api).
const API_BASE_URL = (
    process.env.API_BASE_URL ||
    process.env.INTERNAL_API_BASE_URL ||
    "http://localhost:8000/api"
).replace(/\/$/, "");
const pathPublic: string[] = publicRouters;

const rolePaths: Record<Role, string[]> = {
    [Role.Admin]: ["/admin", "/premium", ...pathPublic, "/nang-cap-hoi-vien"],
    [Role.Premium]: ["/premium", "/user", ...pathPublic],
    [Role.User]: [
        "/user",
        "/nang-cap-hoi-vien",
        ...pathPublic,
        "/payment",
    ],
    [Role.Guest]: [...pathPublic, "/nang-cap-hoi-vien"],
};

export async function proxy(req: NextRequest) {
    const { pathname } = req.nextUrl;
    const accessToken = req.cookies.get("accessToken")?.value;
    const refreshToken = req.cookies.get("refreshToken")?.value;
    if (pathname.match(/\.(png|jpg|jpeg|svg|gif|webp)$/i)) {
        return NextResponse.next();
    }

    let role = Role.Guest;
    if (accessToken) {
        try {
            const decoded: any = jwt.verify(accessToken, SECRET_KEY);
            role = decoded?.role || Role.Guest;
        } catch (err: any) {
            if (err.name === "TokenExpiredError" && refreshToken) {
                try {
                    const refreshRes = await fetch(
                        `${API_BASE_URL}/auth/refresh-token`,
                        {
                            method: "POST",
                            headers: {
                                "Content-Type": "application/json",
                            },
                            body: JSON.stringify({ refreshToken }),
                        }
                    );
                    if (refreshRes.ok) {
                        const resData = await refreshRes.json();
                        const tokens = resData?.data?.tokens;
                        const user = resData?.data?.user;
                        role = user?.role || Role.Guest;

                        const response = NextResponse.next();
                        if (tokens?.accessToken) {
                            response.cookies.set(
                                "accessToken",
                                tokens.accessToken,
                                {
                                    // httpOnly: true,
                                    path: "/",
                                    maxAge: 60 * 15,
                                }
                            );
                        }
                        return response;
                    }
                } catch (e) {
                    console.log("🔥 REFRESH FETCH ERROR:", e);
                    role = Role.Guest;
                }
            } else {
                role = Role.Guest;
            }
        }
    } else if (!accessToken && refreshToken) {
        try {
            const refreshRes = await fetch(
                `${API_BASE_URL}/auth/refresh-token`,
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                    },
                    body: JSON.stringify({ refreshToken }),
                }
            );
            if (refreshRes.ok) {
                const resData = await refreshRes.json();
                const tokens = resData?.data?.tokens;
                const user = resData?.data?.user;
                role = user?.role || Role.Guest;

                const response = NextResponse.next();
                if (tokens?.accessToken) {
                    response.cookies.set("accessToken", tokens.accessToken, {
                        // httpOnly: true,
                        path: "/",
                        maxAge: 60 * 15,
                    });
                }

                return response;
            }
        } catch (e) {
            console.log("🔥 REFRESH FETCH ERROR:", e);
            role = Role.Guest;
        }
    } else {
        role = Role.Guest;
    }

    if (pathname === "/") {
        return NextResponse.next();
    }

    // if (role !== Role.Guest && checkAccessTokenRemove === 1) {
    //     return NextResponse.redirect(new URL("/", req.url));
    // }

    if (pathname === "/login" && role !== Role.Guest) {
        return NextResponse.redirect(new URL("/", req.url));
    }

    if (pathname === "/admin" && role === Role.Guest) {
        return NextResponse.redirect(new URL("/login", req.url));
    }

    // if (pathPublic.includes(pathname)) {
    //     return NextResponse.next();
    // }

    const allowedPaths = rolePaths[role] || rolePaths[Role.Guest];
    const canAccess = allowedPaths.some((path) => pathname.startsWith(path));
    if (!canAccess) {
        return NextResponse.redirect(new URL("/not-found", req.url));
    }

    return NextResponse.next();
}

export const config = {
    matcher: ["/((?!api|python_api|_next/static|_next/image|favicon.ico).*)"],
};
// export const runtime = "nodejs";
// import { NextResponse } from "next/server";
// import type { NextRequest } from "next/server";

// export function proxy(req: NextRequest) {
//     return NextResponse.next();
// }

// export const config = {
//     matcher: ["/((?!_next).*)"],
// };
