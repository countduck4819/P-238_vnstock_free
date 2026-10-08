import {
  Body,
  Controller,
  Delete,
  Get,
  Inject,
  Param,
  Post,
  Put,
  Query,
} from '@nestjs/common';
import { IndustryDto } from './industries.dto';
import { IndustryService } from './industries.service';
import { IndustryServiceToken, UserRole } from 'src/shared';
import { Roles } from 'src/shared/decorator/roles.decorator';
import { ApiBearerAuth } from '@nestjs/swagger';
import { Public } from 'src/shared/decorator/is-public.decorator';

@ApiBearerAuth()
@Controller('/industries')
@Roles(UserRole.ADMIN)
export class IndustryController {
  constructor(
    @Inject(IndustryServiceToken)
    protected industryService: IndustryService,
  ) {}

  @Get('/vnstock')
  @Public()
  getIndustries() {
    return this.industryService.getIndustries();
  }

  @Get('/get-stocks-by-industries')
  @Public()
  getStocksByIndustries() {
    return this.industryService.getStocksByIndustries();
  }

  // Lấy danh sách hoặc tìm theo điều kiện
  @Get()
  getAll(@Query() condition: Record<string, any>) {
    return this.industryService.find(condition);
  }

  // Lấy chi tiết 1 ngành theo id
  @Get(':id')
  get(@Param('id') id: number) {
    return this.industryService.findOne(id);
  }

  // Tạo mới ngành
  @Post()
  create(@Body() dto: IndustryDto) {
    return this.industryService.create(dto);
  }

  // Cập nhật ngành theo id
  @Put(':id')
  update(@Param('id') id: number, @Body() dto: IndustryDto) {
    return this.industryService.updateOne(id, dto);
  }

  // Xóa mềm ngành
  @Delete(':id')
  remove(@Param('id') id: number) {
    return this.industryService.softDelete(id);
  }
}
