import { PassportStrategy } from "@nestjs/passport";
import { Injectable } from "@nestjs/common";
import { Strategy, Profile, VerifyCallback } from "passport-facebook";

@Injectable()
export class FacebookStrategy extends PassportStrategy(Strategy, "facebook") {
  constructor() {
    super({
      clientID: process.env.FACEBOOK_CLIENT_ID,
      clientSecret: process.env.FACEBOOK_CLIENT_SECRET,
      callbackURL: process.env.FACEBOOK_CALLBACK_URL,
      profileFields: ["id", "emails", "name", "photos"],
    });
  }

  async validate(
    accessToken: string,
    refreshToken: string,
    profile: Profile,
    done: VerifyCallback,
  ): Promise<any> {
    const { id, name, emails, photos } = profile;
    const user = {
      provider: "facebook",
      providerId: id,
      email: emails?.[0]?.value,
      name: `${name?.givenName} ${name?.familyName}`,
      avatar: photos?.[0]?.value,
    };
    done(null, user);
  }
}
