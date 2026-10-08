// import { Controller, Post, Body, Inject } from '@nestjs/common';
// import { FastifyReply } from 'fastify';
// import { PayOSService } from './payos.service';

// @Controller('payos')
// export class PayOSController {
//   constructor(private readonly payOSService: PayOSService) {}

//   @Post('create-payment-link')
//   async createPayment(@Body() body: any, @Inject('REPLY') reply: FastifyReply) {
//     try {
//       const { amount } = body; // bạn truyền từ FE vào

//       const paymentLink = await this.payOSService.createPaymentLink(amount);

//       return reply.redirect(paymentLink.checkoutUrl);
//     } catch (e) {
//       console.log(e);
//       return reply.send({ success: false, message: 'Error creating payment' });
//     }
//   }
// }
