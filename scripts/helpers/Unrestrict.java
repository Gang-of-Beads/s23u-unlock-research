package dev.pi.unrestrict;

import java.lang.reflect.Method;

public class Main {
    public static void main(String[] a) throws Exception {
        String[] stubs = {"android.os.IUserManager$Stub", "android.content.pm.IUserManager$Stub", "android.os.IUserManagerService$Stub"};
        Object binder = Class.forName("android.os.ServiceManager").getMethod("getService", String.class).invoke(null, "user");
        Object ium = null;
        for (String s : stubs) {
            try {
                Class<?> stu = Class.forName(s);
                ium = stu.getMethod("asInterface", Class.forName("android.os.IBinder")).invoke(null, binder);
                System.out.println("stub=" + s);
                break;
            } catch (Throwable t) { System.out.println("miss " + s); }
        }
        if (ium == null) return;
        Method set = null;
        for (Method m : ium.getClass().getMethods()) {
            if (m.getName().equals("setUserRestriction") && m.getParameterCount() == 3) { set = m; break; }
        }
        if (set == null) { System.out.println("no setUserRestriction"); return; }
        System.out.println("sig=" + set);
        set.invoke(ium, "no_oem_unlock", false, 0);
        System.out.println("done");
    }
}
