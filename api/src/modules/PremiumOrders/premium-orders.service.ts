import {
  Inject,
  Injectable,
  Logger,
  OnModuleInit,
  ServiceUnavailableException,
} from '@nestjs/common';
import { Repository } from 'typeorm';
import { BaseServices } from '../Base/base.services';
import { PremiumOrderEntity } from './premium-orders.entities';

import {
  BaseResDataI,
  HttpStatusCode,
  ResponseCode,
  UsersRepository,
  AccountType,
  PremiumOrderStatus,
  PremiumOrdersRepository,
} from 'src/shared';

import {
  CreatePremiumOrderDto,
  UpdatePremiumOrderStatusDto,
} from './premium-orders.dto';
import { PremiumOrderResI } from 'src/shared/type/premium-orders';
import { PayOS, type Webhook, type WebhookData } from '@payos/node';

@Injectable()
export class PremiumOrdersService
  extends BaseServices<PremiumOrderEntity>
  implements OnModuleInit
{
  private readonly logger = new Logger(PremiumOrdersService.name);
  private readonly payOS: PayOS | null;

  constructor(
    @Inject(PremiumOrdersRepository)
    protected readonly orderRepo: Repository<PremiumOrderEntity>,

    @Inject(UsersRepository)
    protected readonly userRepo: Repository<any>,
  ) {
    super(orderRepo);

    const { PAYOS_CLIENT_ID, PAYOS_API_KEY, PAYOS_CHECKSUM_KEY } = process.env;
    this.payOS =
      PAYOS_CLIENT_ID && PAYOS_API_KEY && PAYOS_CHECKSUM_KEY
        ? new PayOS({
            clientId: PAYOS_CLIENT_ID,
            apiKey: PAYOS_API_KEY,
            checksumKey: PAYOS_CHECKSUM_KEY,
          })
        : null;
    if (!this.payOS) {
      this.logger.warn(
        'PayOS credentials are absent; Premium payment is unavailable but the API remains online.',
      );
    }
  }

  private requirePayOS(): PayOS {
    if (!this.payOS) {
      throw new ServiceUnavailableException(
        'Premium payment is not configured for this deployment.',
      );
    }
    return this.payOS;
  }

  private generateOrderCode() {
    const now = new Date();
    return (
      now.getFullYear().toString() +
      String(now.getMonth() + 1).padStart(2, '0') +
      String(now.getDate()).padStart(2, '0') +
      String(now.getHours()).padStart(2, '0') +
      String(now.getMinutes()).padStart(2, '0') +
      String(now.getSeconds()).padStart(2, '0')
    );
  }

  async createPremiumOrder(dto: CreatePremiumOrderDto) {
    try {
      const payOS = this.requirePayOS();
      const orderCode = this.generateOrderCode();
      const user = await this.userRepo.findOne({
        where: { id: dto.userId },
      });

      if (!user) {
        return {
          status: HttpStatusCode.NOT_FOUND,
          code: ResponseCode.ERROR,
          message: 'Không tìm thấy user',
          data: null,
        };
      }

      const amount = dto.amount || Number(process.env.PREMIUM_PRICE);

      const order = await this.orderRepo.save({
        orderCode,
        userId: dto.userId,
        amount: amount,
        status: PremiumOrderStatus.PENDING,
      });

      const body = {
        orderCode: Number(orderCode),
        amount: amount,
        description: `Premium ${user?.fullName}`,
        returnUrl: `${process.env.DOMAIN_WEB}/payment/success`,
        cancelUrl: `${process.env.DOMAIN_WEB}/payment/cancel`,
      };

      const payLink = await payOS.paymentRequests.create(body);

      return {
        status: HttpStatusCode.OK,
        code: ResponseCode.SUCCESS,
        message: 'Tạo hóa đơn Premium thành công',
        data: { payLink, order },
      };
    } catch (e) {
      this.logger.error('Lỗi khi tạo hóa đơn Premium:', e);
      return {
        status: HttpStatusCode.INTERNAL_ERROR,
        code: ResponseCode.ERROR,
        message: (e as Error).message,
        data: null,
      };
    }
  }

  async findPaginated(
    query: Record<string, any>,
  ): Promise<BaseResDataI<PremiumOrderResI[] | null>> {
    try {
      const page = Number(query.page) || 1;
      const limit = Number(query.limit) || 10;

      const { page: _p, limit: _l, search, ...condition } = query;

      const qb = this.orderRepo
        .createQueryBuilder('order')
        .leftJoinAndSelect('order.user', 'user')
        .orderBy('order.id', 'DESC')
        .skip((page - 1) * limit)
        .take(limit);

      if (condition.status) {
        qb.andWhere('order.status = :status', { status: condition.status });
      }

      if (condition.fullName?.trim()) {
        qb.andWhere('user.fullName ILIKE :fullName', {
          fullName: `%${condition.fullName.trim()}%`,
        });
      }

      if (condition.orderCode) {
        qb.andWhere('order.orderCode ILIKE :orderCode', {
          orderCode: `%${condition.orderCode}%`,
        });
      }

      const [data, total] = await qb.getManyAndCount();

      return {
        status: HttpStatusCode.OK,
        code: ResponseCode.SUCCESS,
        message: 'Lấy danh sách hóa đơn Premium thành công',
        data: data as any,
        meta: {
          page,
          limit,
          total,
          totalPages: Math.ceil(total / limit),
        },
      };
    } catch (error) {
      this.logger.error('Lỗi findPaginated Premium Order:', error);
      return {
        status: HttpStatusCode.INTERNAL_ERROR,
        code: ResponseCode.ERROR,
        message: (error as Error).message,
        data: null,
      };
    }
  }

  // async handleWebhook(body: any) {
  //   console.log('web hook chayj chuwa')
  //   try {
  //     const verified = this.payOS.webhooks.verify(body);
  //     if (!verified) return { ok: false };
  //   } catch (error) {
  //     this.logger.error('Lỗi verify webhook:', error);
  //     return { ok: false };
  //   }

  //   const { data } = body;
  //   const { orderCode, amount, status, transactionId, paymentMethod } = data;

  //   let internalStatus: PremiumOrderStatus;

  //   if (status === 'PAID') internalStatus = PremiumOrderStatus.PAID;
  //   else if (status === 'CANCELLED') internalStatus = PremiumOrderStatus.CANCEL;
  //   else return { ok: true };

  //   const order = await this.orderRepo.findOne({ where: { orderCode } });
  //   if (!order) return { ok: false };

  //   if (+(order?.amount || Number(process.env.PREMIUM_PRICE)) !== +amount) {
  //     this.logger.error(
  //       `Số tiền không khớp: DB=${order.amount} vs PayOS=${amount}`,
  //     );
  //     return { ok: false };
  //   }

  //   if (order.status === PremiumOrderStatus.PAID) {
  //     return { ok: true };
  //   }

  //   await this.orderRepo.update(
  //     { id: order.id },
  //     {
  //       status: internalStatus,
  //       transactionId,
  //       paymentMethod,
  //     },
  //   );

  //   if (internalStatus === PremiumOrderStatus.PAID) {
  //     await this.userRepo.update(order.userId, {
  //       accountType: AccountType.PREMIUM,
  //     });
  //   }

  //   return { ok: true };
  // }
  async handleWebhook(body: Webhook) {
    this.logger.log('=== WEBHOOK RECEIVED ===');

    if (!body) {
      this.logger.error('Body is undefined or null');
      return { ok: false, error: 'Empty body' };
    }

    try {
      const payOS = this.requirePayOS();
      let verifiedData: WebhookData;

      try {
        verifiedData = await payOS.webhooks.verify(body);
        this.logger.log('✅ Webhook verified successfully');
      } catch (verifyError) {
        const message =
          verifyError instanceof Error
            ? verifyError.message
            : String(verifyError);

        this.logger.error(`Webhook verify error: ${message}`);
        return { ok: false, error: 'Invalid webhook signature' };
      }

      const {
        orderCode,
        amount,
        reference,
        transactionDateTime,
        counterAccountBankName,
        counterAccountNumber,
        description,
      } = verifiedData;

      const { success } = body;

      this.logger.log(`Processing order ${orderCode} - Success: ${success}`);

      // ✅ Validate required fields
      if (!orderCode || !amount) {
        this.logger.error('Missing required fields:', { orderCode, amount });
        return { ok: false, error: 'Missing required fields' };
      }

      // ✅ Xác định trạng thái dựa trên success
      let internalStatus: PremiumOrderStatus;

      if (success === true) {
        internalStatus = PremiumOrderStatus.PAID;
        this.logger.log('✅ Payment successful');
      } else {
        internalStatus = PremiumOrderStatus.CANCEL;
        this.logger.log('❌ Payment failed/cancelled');
      }

      // ✅ Tìm order trong database
      const order = await this.orderRepo.findOne({
        where: { orderCode: orderCode.toString() },
      });

      if (!order) {
        this.logger.error(`Order not found: ${orderCode}`);
        return { ok: false, error: 'Order not found' };
      }

      this.logger.log('Order found:', {
        id: order.id,
        orderCode: order.orderCode,
        userId: order.userId,
        amount: order.amount,
        currentStatus: order.status,
      });

      // ✅ Kiểm tra số tiền
      if (+(order?.amount || Number(process.env.PREMIUM_PRICE)) !== +amount) {
        this.logger.error(
          `Số tiền không khớp: DB=${order.amount} vs PayOS=${amount}`,
        );
        return { ok: false, error: 'Amount mismatch' };
      }

      // ✅ Nếu đã thanh toán rồi thì skip
      if (order.status === PremiumOrderStatus.PAID) {
        this.logger.log(`Order ${orderCode} already paid, skipping...`);
        return { ok: true, message: 'Already processed' };
      }

      // ✅ Cập nhật order
      await this.orderRepo.update(
        { id: order.id },
        {
          status: internalStatus,
          transactionId: reference,
          paymentMethod: counterAccountBankName || 'BANK_TRANSFER',
        },
      );

      this.logger.log(`✅ Order ${orderCode} updated to ${internalStatus}`);

      // ✅ Nếu thanh toán thành công, nâng cấp user lên Premium
      if (internalStatus === PremiumOrderStatus.PAID) {
        const user = await this.userRepo.findOne({
          where: { id: order.userId },
        });

        if (!user) {
          this.logger.error(`User not found: ${order.userId}`);
          return { ok: false, error: 'User not found' };
        }

        // Kiểm tra user đã Premium chưa
        if (user.accountType === AccountType.PREMIUM) {
          this.logger.log(`User ${order.userId} is already PREMIUM`);
        } else {
          // Cập nhật user lên Premium
          await this.userRepo.update(order.userId, {
            accountType: AccountType.PREMIUM,
          });

          this.logger.log(
            `✅ User ${order.userId} (${user.username}) upgraded to PREMIUM`,
          );
        }

        // Log chi tiết giao dịch
        this.logger.log('✅ Transaction completed:', {
          orderCode,
          amount,
          reference,
          transactionDateTime,
          bank: counterAccountBankName,
          accountNumber: counterAccountNumber,
          description,
        });
      }

      return {
        ok: true,
        message: 'Webhook processed successfully',
        orderCode,
        status: internalStatus,
      };
    } catch (error) {
      this.logger.error('❌ Exception in handleWebhook:', error);
      this.logger.error('Stack:', error.stack);
      return { ok: false, error: error.message };
    }
  }

  async onModuleInit() {
    this.logger.log('PremiumOrdersService initialized.');
  }

  async updatePremiumOrder(
    id: number,
    dto: UpdatePremiumOrderStatusDto,
  ): Promise<BaseResDataI<any>> {
    try {
      const order = await this.orderRepo.findOne({ where: { id } });
      if (!order) {
        return {
          status: HttpStatusCode.NOT_FOUND,
          code: ResponseCode.ERROR,
          message: 'Không tìm thấy hóa đơn',
          data: null,
        };
      }

      await this.orderRepo.update({ id }, dto);

      const updated = await this.orderRepo.findOne({ where: { id } });

      return {
        status: HttpStatusCode.OK,
        code: ResponseCode.SUCCESS,
        message: 'Cập nhật hóa đơn thành công',
        data: updated,
      };
    } catch (error) {
      this.logger.error('Lỗi update Premium Order:', error);
      return {
        status: HttpStatusCode.INTERNAL_ERROR,
        code: ResponseCode.ERROR,
        message: (error as Error).message,
        data: null,
      };
    }
  }

  async deletePremiumOrder(id: number): Promise<BaseResDataI<any>> {
    try {
      const order = await this.orderRepo.findOne({ where: { id } });
      if (!order) {
        return {
          status: HttpStatusCode.NOT_FOUND,
          code: ResponseCode.ERROR,
          message: 'Không tìm thấy hóa đơn',
          data: null,
        };
      }

      await this.orderRepo.delete(id);

      return {
        status: HttpStatusCode.OK,
        code: ResponseCode.SUCCESS,
        message: 'Xóa hóa đơn thành công',
        data: { id },
      };
    } catch (error) {
      this.logger.error('Lỗi delete Premium Order:', error);
      return {
        status: HttpStatusCode.INTERNAL_ERROR,
        code: ResponseCode.ERROR,
        message: (error as Error).message,
        data: null,
      };
    }
  }
}
