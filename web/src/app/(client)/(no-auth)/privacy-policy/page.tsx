export default function PrivacyPolicy() {
    return (
        <section className="min-h-screen bg-gradient-to-b from-gray-50 to-white dark:from-slate-950 dark:to-slate-900 flex items-center justify-center py-16 px-4 transition-colors duration-300">
            <div className="max-w-3xl w-full bg-white dark:bg-slate-900 shadow-xl rounded-2xl p-8 sm:p-10 border border-gray-100 dark:border-slate-800">
                <h1 className="text-3xl font-bold text-center text-gray-800 dark:text-white mb-8">
                    Chính sách Quyền riêng tư
                </h1>

                <div className="space-y-5 text-gray-700 dark:text-slate-300 leading-relaxed text-sm sm:text-base">
                    <p>
                        <strong className="text-gray-900 dark:text-white">Chúng tôi thu thập:</strong> tên{" "}
                        <b className="text-gray-900 dark:text-white">Vũ Thành Khang</b>, email{" "}
                        <a
                            href="mailto:17loiten@gmail.com"
                            className="text-indigo-600 dark:text-indigo-400 hover:underline"
                        >
                            17loiten@gmail.com
                        </a>
                        .
                    </p>

                    <p>
                        <strong className="text-gray-900 dark:text-white">Mục đích:</strong> xác thực người dùng, chăm sóc
                        khách hàng, và cải thiện chất lượng dịch vụ.
                    </p>

                    <p>
                        <strong className="text-gray-900 dark:text-white">Lưu trữ & chia sẻ:</strong> dữ liệu được lưu trữ
                        an toàn trên máy chủ của chúng tôi; chúng tôi{" "}
                        <b className="text-gray-900 dark:text-white">không chia sẻ</b> thông tin cá nhân của bạn cho bên
                        thứ ba.
                    </p>

                    <p>
                        <strong className="text-gray-900 dark:text-white">Quyền của bạn:</strong> bạn có thể yêu cầu xem,
                        sửa, hoặc xóa dữ liệu cá nhân của mình bằng cách gửi
                        email đến:{" "}
                        <a
                            href="mailto:17loiten@gmail.com"
                            className="text-indigo-600 dark:text-indigo-400 hover:underline"
                        >
                            17loiten@gmail.com
                        </a>
                    </p>

                    <p>
                        <strong className="text-gray-900 dark:text-white">Cookie:</strong> chúng tôi sử dụng cookie
                        HTTP-only để đảm bảo an toàn trong quá trình đăng nhập.
                    </p>

                    <p>
                        <strong className="text-gray-900 dark:text-white">Liên hệ:</strong> Nhà 21, ngõ 44, phố Đại Linh,
                        Trung Văn, Hà Nội. <br />
                        Email:{" "}
                        <a
                            href="mailto:17loiten@gmail.com"
                            className="text-indigo-600 dark:text-indigo-400 hover:underline"
                        >
                            17loiten@gmail.com
                        </a>
                    </p>

                    <p className="text-xs sm:text-sm text-gray-500 dark:text-slate-400 border-t border-gray-100 dark:border-slate-800 pt-4 mt-6">
                        <em>Cập nhật lần cuối: 22/10/2025</em>
                    </p>
                </div>
            </div>
        </section>
    );
}
