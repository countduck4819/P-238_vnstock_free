import express from "express";
import passport from "passport";

export const googleExpress = express.Router();

googleExpress.get(
  "/auth/google",
  passport.authenticate("google", { scope: ["profile", "email"] }),
);

googleExpress.get(
  "/auth/google/callback",
  passport.authenticate("google", { session: false }),
  (req, res) => {
    const user = req.user as any;

    res.cookie("accessToken", user.accessToken, {
      httpOnly: false,
      sameSite: "lax",
      path: "/",
    });

    return res.redirect(`${process.env.DOMAIN_WEB}/login?g=1`);
  },
);
