package com.github.diegopacheco.temporaletl;

import io.temporal.worker.WorkerFactory;

public class WorkerMain {

    public static void main(String[] args) throws Exception {
        Db.init();
        String identity = "etl-worker-pid-" + ProcessHandle.current().pid();
        var factory = WorkerFactory.newInstance(Temporal.client(identity));
        var worker = factory.newWorker(Config.TASK_QUEUE);
        worker.registerWorkflowImplementationTypes(EtlWorkflowImpl.class);
        worker.registerActivitiesImplementations(new EtlActivitiesImpl());
        factory.start();
        System.out.println("worker started identity=" + identity + " taskQueue=" + Config.TASK_QUEUE);
        Runtime.getRuntime().addShutdownHook(new Thread(factory::shutdown));
        Thread.currentThread().join();
    }
}
