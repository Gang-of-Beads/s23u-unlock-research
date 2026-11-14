import java.lang.reflect.*;

public class Em {
    static final String IFACE = "vendor.samsung.hardware.security.engmode@1.0::ISehEngmode";

    public static void main(String[] a) throws Exception {
        Class<?> HB = Class.forName("android.os.HwBinder");
        Class<?> P = Class.forName("android.os.Parcel");
        Object b = HB.getMethod("getService", String.class, String.class).invoke(null, IFACE, "default");
        System.out.println("binder=" + b);
        if (b == null) return;
        Method transact = HB.getMethod("transact", int.class, P, P, int.class);
        Method obtain = P.getMethod("obtain");
        Method writeIfToken = P.getMethod("writeInterfaceToken", String.class);
        Method setPos = P.getMethod("setDataPosition", int.class);
        Method size = P.getMethod("dataSize");
        Method avail = P.getMethod("dataAvail");
        Method readByte = P.getMethod("readByte");
        Method recycle = P.getMethod("recycle");
        int from = a.length > 0 ? Integer.parseInt(a[0]) : 1;
        int to = a.length > 1 ? Integer.parseInt(a[1]) : 22;
        for (int code = from; code <= to; code++) {
            Object d = obtain.invoke(null), r = obtain.invoke(null);
            try {
                writeIfToken.invoke(d, IFACE);
                Object ok = transact.invoke(b, code, d, r, 0);
                setPos.invoke(r, 0);
                int n = (Integer) size.invoke(r);
                int av = (Integer) avail.invoke(r);
                StringBuilder sb = new StringBuilder();
                for (int i = 0; i < av && i < 200; i++) sb.append(String.format("%02x", ((Byte) readByte.invoke(r)) & 0xff));
                System.out.println("code " + code + " ret=" + ok + " size=" + n + " " + sb);
            } catch (Throwable t) {
                System.out.println("code " + code + " EX " + (t.getCause() != null ? t.getCause() : t));
            } finally { recycle.invoke(d); recycle.invoke(r); }
        }
    }
}
