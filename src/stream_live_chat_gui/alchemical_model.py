from PyQt5.QtWidgets import QMessageBox
from PyQt5.QtCore import QAbstractTableModel, QVariant, QModelIndex, Qt
from stream_live_chat_gui import AlchemizedModelColumn
from sqlalchemy.orm import joinedload
import logging

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


# https://gist.github.com/harvimt/4699169
class AlchemicalTableModel(QAbstractTableModel):
    """A Qt Table Model that binds to an SQL Alchemy Query"""

    def __init__(self, session, model, relationship, columns):
        super().__init__()
        # TODO: session and model might not be needed if just an instance of 'DBInteractions' is passed
        self.session = session()
        self.relationship = relationship
        self.query = self.session.query(model)
        log.debug(f"Passed columns: {columns}")
        self.fields: list[AlchemizedModelColumn] = columns

        self.results = None
        self.count = None
        self.sort = None
        self.filter = None

        self.refresh()

    def headerData(self, column, orientation, role):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            header = (
                self.fields[column].column_name
                if not self.fields[column].header_display_name
                else self.fields[column].header_display_name
            )
            return QVariant(header)
        return QVariant()

    def setFilter(self, filter):
        """Sets or clears the filter, clear the filter by default is set to None"""
        log.info(f"Setting filter to: {filter}")
        self.filter = filter
        self.refresh()

    def refresh(self):
        """Recalculates self.results and self.count"""
        log.info("Refreshing the table")
        self.layoutAboutToBeChanged.emit()
        query = self.query
        if self.sort is not None:
            order, column = self.sort
            column = self.fields[column].column
            if order == Qt.DescendingOrder:
                column = column.desc()
        else:
            column = None

        if self.filter is not None:
            query = query.filter(self.filter)

        query = query.order_by(column)

        self.results = query.options(
            joinedload(self.relationship, innerjoin=True)
        ).all()
        self.count = query.count()
        self.layoutChanged.emit()

    def flags(self, index):
        flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable

        if self.sort is not None:
            order, column = self.sort

            if self.fields[column].flags.get("dnd", False) and index.column() == column:
                flags |= Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled

        if self.fields[index.column()].flags.get("editable", False):
            flags |= Qt.ItemIsEditable

        return flags

    def supportedDropActions(self):
        return Qt.MoveAction

    def rowCount(self, parent=QModelIndex()):
        return self.count or 0

    def columnCount(self, parent=QModelIndex()):
        return len(self.fields)

    def data(self, index, role):
        if not index.isValid() or role not in (Qt.DisplayRole, Qt.EditRole):
            return QVariant()
        row = self.results[index.row()]
        name = self.fields[index.column()].column_name
        value = str(getattr(row, name))
        return value

    def setData(self, index, value, role=None) -> bool:
        row = self.results[index.row()]
        name = self.fields[index.column()].column_name

        try:
            setattr(row, name, value.toString())
            self.session.commit()
        except Exception as e:
            QMessageBox.critical(None, "SQL Input Error", str(e))
            return False
        else:
            self.dataChanged.emit(index, index)
            return True

    def setSorting(self, column, order=Qt.DescendingOrder):
        """Sort table by given column number."""
        self.sort = order, column
        self.refresh()
