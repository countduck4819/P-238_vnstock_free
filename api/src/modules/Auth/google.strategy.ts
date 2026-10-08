import { PassportStrategy } from "@nestjs/passport";
import { Injectable } from "@nestjs/common";
import { Strategy, VerifyCallback } from "passport-google-oauth20";

// // @Injectable()
// // export class GoogleStrategy extends PassportStrategy(Strategy, 'google') {
// //   constructor() {
// //     super({
// //       clientID: process.env.GOOGLE_CLIENT_ID,
// //       clientSecret: process.env.GOOGLE_CLIENT_SECRET,
// //       callbackURL: process.env.GOOGLE_CALLBACK_URL,
// //       scope: ['email', 'profile'],
// //     });
// //   }

// //   async validate(accessToken: string, refreshToken: string, profile: any, done: VerifyCallback) {
// //     const { name, emails, photos } = profile;
// //     const user = {
// //       provider: 'google',
// //       providerId: profile.id,
// //       email: emails?.[0]?.value,
// //       name: `${name?.givenName} ${name?.familyName}`,
// //       avatar: photos?.[0]?.value,
// //     };
// //     done(null, user);
// //   }
// // }

// // import { PassportStrategy } from '@nestjs/passport';
// // import { Strategy, VerifyCallback } from 'passport-google-oauth20';
// // import { Injectable } from '@nestjs/common';

@Injectable()
export class GoogleStrategy extends PassportStrategy(Strategy, "google") {
  constructor() {
    super({
      // OAuth is optional for a deployment. The guard rejects Google-login
      // requests when these values are absent, while password login and the
      // rest of the API remain available.
      clientID: process.env.GOOGLE_CLIENT_ID || "google-oauth-disabled",
      clientSecret:
        process.env.GOOGLE_CLIENT_SECRET || "google-oauth-disabled",
      callbackURL:
        process.env.GOOGLE_CALLBACK_URL ||
        "http://localhost:8000/api/auth/google/callback",
      scope: ["email", "profile"],
    });
  }

  async validate(accessToken, refreshToken, profile, done: VerifyCallback) {
    const user = {
      email: profile.emails[0].value,
      name: profile.displayName,
      avatar: profile.photos[0].value,
      accessToken,
    };

    done(null, user);
  }
}

// google.strategy.ts - SỬA LẠI
// import { PassportStrategy } from '@nestjs/passport';
// import { Strategy, VerifyCallback } from 'passport-google-oauth20';
// import { Injectable } from '@nestjs/common';

// @Injectable()
// export class GoogleStrategy extends PassportStrategy(Strategy, 'google') {
//   constructor() {
//     super({
//       clientID: process.env.GOOGLE_CLIENT_ID,
//       clientSecret: process.env.GOOGLE_CLIENT_SECRET,
//       callbackURL: 'http://localhost:3000/api/auth/google/callback', // CHÚ Ý: có /api
//       scope: ['email', 'profile'],
//     });
//   }

//   async validate(
//     accessToken: string,
//     refreshToken: string,
//     profile: any,
//     done: VerifyCallback,
//   ): Promise<any> {
//     const user = {
//       email: profile.emails[0].value,
//       name: profile.displayName,
//       avatar: profile.photos[0].value,
//     };

//     done(null, user);
//   }
// }
