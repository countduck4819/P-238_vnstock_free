// import { Injectable } from '@nestjs/common';
// import PayOS from '@payos/node';

// @Injectable()
// export class PayOSService {
//   protected payOS: any;

//   constructor() {
//     this.payOS = new PayOS(
//       process.env.PAYOS_CLIENT_ID,
//       process.env.PAYOS_API_KEY,
//       process.env.PAYOS_CHECKSUM_KEY,
//     );
//   }

//   /** Sinh orderCode dạng YYYYMMDDHHMMSS */
//   protected generateOrderCode() {
//     const now = new Date();

//     const yyyy = now.getFullYear();
//     const MM = String(now.getMonth() + 1).padStart(2, '0');
//     const dd = String(now.getDate()).padStart(2, '0');

//     const hh = String(now.getHours()).padStart(2, '0');
//     const mm = String(now.getMinutes()).padStart(2, '0');
//     const ss = String(now.getSeconds()).padStart(2, '0');

//     return Number(`${yyyy}${MM}${dd}${hh}${mm}${ss}`);
//   }

//   /** Tạo link thanh toán Premium */
//   async createPremiumPaymentLink() {
//     const orderCode = this.generateOrderCode();

//     const PREMIUM_PRICE = Number(process.env.PREMIUM_PRICE || 1000);

//     const body = {
//       orderCode,
//       amount: PREMIUM_PRICE,
//       description: 'Thanh toán gói hội viên Premium',
//       items: [
//         {
//           name: 'Gói hội viên Premium',
//           quantity: 1,
//           price: PREMIUM_PRICE,
//         },
//       ],
//       returnUrl: `${process.env.DOMAIN}/payment/success`,
//       cancelUrl: `${process.env.DOMAIN}/payment/cancel`,
//     };

//     return this.payOS.createPaymentLink(body);
//   }
// }
