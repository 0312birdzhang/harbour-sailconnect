#pragma once
#include <QCoreApplication>
#include <QString>

class StatusText {
    Q_DECLARE_TR_FUNCTIONS(StatusText)
public:
    static QString state(const QString &value);
    static QString error(const QString &value);
    static QString phase(const QString &value);
};
