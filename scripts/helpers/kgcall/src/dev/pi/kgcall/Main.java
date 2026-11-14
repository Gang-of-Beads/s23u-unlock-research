package dev.pi.kgcall;

import android.os.IBinder;
import android.os.Parcel;
import java.util.ArrayList;
import java.util.List;

/** 用法: Main <code|!code|seq|brute N|sweep> [int:0|ba:16|str:x ...] */
public class Main {
    static final String SVC = "vendor.samsung.hardware.tlc.kg.ISehKg/default";
    static final String DESC = "vendor.samsung.hardware.tlc.kg.ISehKg";
    static boolean ONE_WAY = false;

    static byte[] callArgs(IBinder b, int code, List<Object> params) throws Exception {
        Parcel d = Parcel.obtain(), r = Parcel.obtain();
        d.writeInterfaceToken(DESC);
        for (Object o : params) {
            if (o instanceof Integer) d.writeInt((Integer) o);
            else if (o instanceof byte[]) d.writeByteArray((byte[]) o);
            else d.writeString(String.valueOf(o));
        }
        b.transact(code, d, r, ONE_WAY ? 1 : 0);
        int avail = r.dataAvail();
        if (avail == 0) {
            System.out.println("code " + code + " no-reply (oneway)");
            r.recycle();
            d.recycle();
            return new byte[0];
        }
        r.readException();
        StringBuilder sb = new StringBuilder();
        byte[] out = new byte[avail];
        int p = 0;
        while (r.dataAvail() >= 4) {
            int v = r.readInt();
            for (int k = 0; k < 4; k++) out[p++] = (byte) ((v >> (8 * k)) & 0xff);
            sb.append(String.format("%08x ", v));
        }
        System.out.println("code " + code + " avail=" + avail + " -> " + sb);
        r.recycle();
        d.recycle();
        return out;
    }

    static byte[] call(IBinder b, int code, byte[] arg, int intArg) throws Exception {
        List<Object> l = new ArrayList<>();
        if (arg != null) l.add(arg); else l.add(intArg);
        return callArgs(b, code, l);
    }

    static void sweep(IBinder b) {
        for (int c = 1; c <= 28; c++) {
            List<Object> l = new ArrayList<>();
            l.add(new byte[16]);
            try { callArgs(b, c, l); } catch (Throwable t) { System.out.println("code " + c + " ERR " + t.getMessage()); }
        }
    }

    static void brute(IBinder b, int code) throws Exception {
        Object[][] combos = {
            {null, 0}, {new byte[16], 0}, {new byte[32], 0}, {new byte[64], 0},
            {new byte[16], 1}, {new byte[8200], 0}, {new byte[16], -1},
        };
        for (Object[] c : combos) {
            try { call(b, code, (byte[]) c[0], (Integer) c[1]); }
            catch (Throwable t) { System.out.println("code " + code + " ERR " + t.getMessage()); }
        }
    }

    static void seq(IBinder b) {
        try {
            byte[] n = call(b, 9, null, 0);
            byte[] nonce = new byte[16];
            if (n.length >= 32) System.arraycopy(n, 12, nonce, 0, 16);
            List<Object> l = new ArrayList<>();
            l.add(nonce);
            l.add(new byte[16]);
            callArgs(b, 10, l);
        } catch (Throwable t) { System.out.println("EXC " + t); }
    }

    public static void main(String[] a) throws Exception {
        IBinder b = (IBinder) Class.forName("android.os.ServiceManager").getMethod("getService", String.class).invoke(null, SVC);
        String mode = a[0];
        if (mode.startsWith("!")) { ONE_WAY = true; mode = mode.substring(1); }
        if (mode.equals("sweep")) { sweep(b); return; }
        if (mode.equals("brute")) { brute(b, Integer.parseInt(a[1])); return; }
        if (mode.equals("seq")) { seq(b); return; }
        int code = Integer.parseInt(mode);
        List<Object> params = new ArrayList<>();
        for (int i = 1; i < a.length; i++) {
            String sp = a[i];
            int c = sp.indexOf(':');
            String kind = c < 0 ? sp : sp.substring(0, c);
            String val = c < 0 ? "" : sp.substring(c + 1);
            if (kind.equals("int")) params.add(Integer.parseInt(val));
            else if (kind.equals("ba")) params.add(new byte[Integer.parseInt(val)]);
            else if (kind.equals("str")) params.add(val);
        }
        callArgs(b, code, params);
    }
}
