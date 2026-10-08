import {
  Body,
  Controller,
  Delete,
  Get,
  Headers,
  Inject,
  Param,
  Post,
  Put,
  Query,
} from "@nestjs/common";
import { UserRole, UsersServiceToken } from "src/shared";
import { UsersService } from "./users.services";
import { UserDTO } from "./users.dto";
import { Roles } from "src/shared/decorator/roles.decorator";
import { Public } from "src/shared/decorator/is-public.decorator";
import { ApiBearerAuth, ApiQuery } from "@nestjs/swagger";

@ApiBearerAuth()
@Controller("/users")
@Roles(UserRole.ADMIN)
export class UsersController {
  constructor(
    @Inject(UsersServiceToken)
    protected usersService: UsersService,
  ) {}

  @Get("query")
  async getAllPagination(
    @Query("page") page = 1,
    @Query("limit") limit = 10,
    @Query() query: Record<string, any> = {},
  ) {
    const { page: _, limit: __, ...filters } = query;
    return this.usersService.paginate({}, Number(page), Number(limit), filters);
  }

  @Get()
  getAll() {
    return this.usersService.find();
  }

  @Roles(UserRole.USER)
  @Get("/:id")
  get(@Param("id") id: number) {
    return this.usersService.findOne(id);
  }

  @Post()
  @Public()
  post(@Body() body: UserDTO) {
    return this.usersService.create(body);
  }

  @Roles(UserRole.USER)
  @Put("/:id")
  put(@Param("id") id: number, @Body() body: UserDTO) {
    return this.usersService.updateOne(id, body);
  }

  @Delete("/:id")
  delete(@Param("id") id: number) {
    return this.usersService.softDelete(id);
  }
}
